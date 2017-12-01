import argparse

from proxy.server import run_server


def parse_args():
    parser = argparse.ArgumentParser(description='Habraproxy')
    parser.add_argument('--port', type=int, nargs='?',
                        help='local port for proxy server')
    parser.add_argument('--host', type=str, nargs='?',
                        help='tagret host for proxy server')

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_server(args.host, args.port)
