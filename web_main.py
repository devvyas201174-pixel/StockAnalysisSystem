import os
import sys
import argparse

from StockAnalysisSystem.webapp.app import create_app


def main():
    parser = argparse.ArgumentParser(description='Run the StockAnalysisSystem local web UI.')
    parser.add_argument('--host', default='127.0.0.1', help='Bind host. Default 127.0.0.1 (local machine only).')
    parser.add_argument('--port', type=int, default=5000, help='Bind port. Default 5000.')
    parser.add_argument('--project-path', default=None,
                        help='Project path containing config.json. Default: current working directory.')
    args = parser.parse_args()

    app = create_app(args.project_path or os.getcwd())
    print('StockAnalysisSystem web UI running at http://%s:%d' % (args.host, args.port))
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Error =>', e)
        sys.exit(1)
