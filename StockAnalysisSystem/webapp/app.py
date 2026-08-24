import os
import datetime

from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, flash

from StockAnalysisSystem.interface.interface_local import LocalInterface
from StockAnalysisSystem.core.Utility.time_utility import text2date

CONFIG_FIELDS = ['NOSQL_DB_HOST', 'NOSQL_DB_PORT', 'NOSQL_DB_USER', 'NOSQL_DB_PASS',
                 'TS_TOKEN', 'PROXY_PROTOCOL', 'PROXY_HOST']


def _parse_date(text: str) -> datetime.datetime or None:
    text = (text or '').strip()
    return text2date(text) if text != '' else None


def _time_serial(since_text: str, until_text: str, since_default=None, until_default=None) -> tuple or None:
    since = _parse_date(since_text) or since_default
    until = _parse_date(until_text) or until_default
    return (since, until) if since is not None or until is not None else None


def _df_to_table(df) -> (list, list):
    if df is None or len(df) == 0:
        return [], []
    return list(df.columns), df.astype(str).values.tolist()


def create_app(project_path: str = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = 'stock-analysis-system-local-web-ui'

    sas_if = LocalInterface()
    sas_if.if_init(project_path or os.getcwd())
    app.config['SAS_IF'] = sas_if

    # ------------------------------------------------------------ Data Hub --

    @app.route('/')
    def data_hub():
        sas_if = app.config['SAS_IF']
        probs = sas_if.sas_get_data_agent_probs()
        rows = []
        for prob in probs:
            uri = prob.get('uri')
            since, until = sas_if.sas_get_data_range(uri, None)
            rows.append({
                'uri': uri,
                'since': since.strftime('%Y-%m-%d') if since else '-',
                'until': until.strftime('%Y-%m-%d') if until else '-',
            })
        rows.sort(key=lambda r: r['uri'])
        return render_template('data_hub.html', rows=rows)

    @app.route('/api/execute_update', methods=['POST'])
    def api_execute_update():
        sas_if = app.config['SAS_IF']
        data = request.get_json(force=True)
        uri = data.get('uri')
        identity = (data.get('identity') or '').strip() or None
        time_serial = _time_serial(data.get('since'), data.get('until'))
        force = bool(data.get('force'))
        res_id = sas_if.sas_execute_update(uri, identity=identity, time_serial=time_serial, force=force)
        return jsonify({'res_id': res_id})

    @app.route('/api/resource_status/<res_id>')
    def api_resource_status(res_id):
        sas_if = app.config['SAS_IF']
        res = sas_if.sas_get_resource([(res_id, ['master'])])
        master = res.get(res_id, {}).get('master')
        finished = master.finished() if master is not None else True
        status = master.status() if master is not None else None
        return jsonify({'finished': finished, 'status': status})

    @app.route('/api/data_range')
    def api_data_range():
        sas_if = app.config['SAS_IF']
        uri = request.args.get('uri', '')
        identity = request.args.get('identity', '') or None
        since, until = sas_if.sas_get_data_range(uri, identity)
        return jsonify({
            'since': since.strftime('%Y-%m-%d') if since else None,
            'until': until.strftime('%Y-%m-%d') if until else None,
        })

    # -------------------------------------------------------------- Browse --

    @app.route('/browse')
    def browse():
        sas_if = app.config['SAS_IF']
        uri = request.args.get('uri', '')
        identity = request.args.get('identity', '')
        since_text = request.args.get('since', '')
        until_text = request.args.get('until', '')

        columns, table, error = [], None, None
        if uri:
            time_serial = _time_serial(since_text, until_text)
            try:
                df = sas_if.sas_query(uri, identity or None, time_serial)
                columns, table = _df_to_table(df)
                if not table:
                    error = 'No data cached for this query.'
            except Exception as e:
                error = str(e)

        return render_template('browse.html', uris=sorted(sas_if.sas_get_all_uri()), uri=uri, identity=identity,
                               since=since_text, until=until_text, columns=columns, table=table, error=error)

    @app.route('/browse/csv')
    def browse_csv():
        sas_if = app.config['SAS_IF']
        uri = request.args.get('uri', '')
        identity = request.args.get('identity', '') or None
        time_serial = _time_serial(request.args.get('since', ''), request.args.get('until', ''))
        df = sas_if.sas_query(uri, identity, time_serial)
        csv_text = df.to_csv(index=False) if df is not None else ''
        filename = (uri or 'data').replace('.', '_') + '.csv'
        return Response(csv_text, mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename=%s' % filename})

    # ------------------------------------------------------------- Analyze --

    @app.route('/analyze')
    def analyze():
        sas_if = app.config['SAS_IF']
        analyzers = sorted(sas_if.sas_get_analyzer_probs(), key=lambda a: a['name'])
        return render_template('analyze.html', analyzers=analyzers)

    @app.route('/api/execute_analysis', methods=['POST'])
    def api_execute_analysis():
        sas_if = app.config['SAS_IF']
        data = request.get_json(force=True)
        securities = [s.strip() for s in (data.get('securities') or '').split(',') if s.strip()]
        analyzers = data.get('analyzers') or []
        time_serial = _time_serial(data.get('since'), data.get('until'),
                                   since_default=datetime.datetime(2015, 1, 1), until_default=datetime.datetime.now())
        res_id = sas_if.sas_execute_analysis(securities, analyzers, time_serial, enable_from_cache=False)
        return jsonify({'res_id': res_id})

    @app.route('/api/analysis_result/<res_id>')
    def api_analysis_result(res_id):
        sas_if = app.config['SAS_IF']
        res = sas_if.sas_get_resource([(res_id, ['master'])])
        master = res.get(res_id, {}).get('master')
        if master is None or not master.finished():
            return jsonify({'finished': False})

        name_dict = {a['uuid']: a['name'] for a in sas_if.sas_get_analyzer_probs()}
        rows = [{
            'method': name_dict.get(r.method, r.method),
            'securities': r.securities,
            'period': str(r.period) if r.period else '-',
            'score': r.score,
            'brief': r.brief,
            'reason': r.reason,
        } for r in (master.result() or [])]
        return jsonify({'finished': True, 'rows': rows})

    # ------------------------------------------------------------- Factors --

    @app.route('/factors')
    def factors():
        sas_if = app.config['SAS_IF']
        identity = request.args.get('identity', '')
        selected = request.args.getlist('factor')
        since_text = request.args.get('since', '')
        until_text = request.args.get('until', '')

        columns, table, error = [], None, None
        if identity and selected:
            time_serial = _time_serial(since_text, until_text,
                                       since_default=datetime.datetime(2015, 1, 1), until_default=datetime.datetime.now())
            try:
                df = sas_if.sas_factor_query(identity, selected, time_serial, {})
                columns, table = _df_to_table(df)
                if not table:
                    error = 'No data.'
            except Exception as e:
                error = str(e)

        return render_template('factors.html', all_factors=sorted(sas_if.sas_get_all_factors()), identity=identity,
                               selected=selected, since=since_text, until=until_text,
                               columns=columns, table=table, error=error)

    # -------------------------------------------------------------- Config --

    @app.route('/config', methods=['GET', 'POST'])
    def config():
        sas_if = app.config['SAS_IF']
        if request.method == 'POST':
            new_config = {k: request.form.get(k, '') for k in CONFIG_FIELDS}
            sas_if.sas_set_service_config(new_config)
            flash('Settings saved.')
            return redirect(url_for('config'))

        current = sas_if.sas_get_service_config()
        return render_template('config.html', config=current, fields=CONFIG_FIELDS)

    return app
