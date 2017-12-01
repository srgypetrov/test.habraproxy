import argparse

from proxy.server import run_server


def parse_args():
    parser = argparse.ArgumentParser(description='Simple http proxy server')
    parser.add_argument('-l', '--local-port', type=int, nargs='?',
                        metavar='PORT', help='proxy server local port')
    parser.add_argument('-t', '--target-host', type=str, nargs='?',
                        metavar='HOST', help='proxy server target host name')
    parser.add_argument('-p', '--target-port', type=int, nargs='?',
                        metavar='PORT', help='proxy server target port.')

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_server(args.local_port, args.target_host, args.target_port)
