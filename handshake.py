#!/usr/bin/env python3
"""Simple handshake script for TCP or UDP.

Client: sends a single hello message and exits.
Server: receives one message, prints the client IP and message, then exits.
"""

from __future__ import annotations

import argparse
import socket


DEFAULT_PORT = 9999
DEFAULT_MESSAGE = "hello"
DEFAULT_RESPONSE = "hello received"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple TCP/UDP handshake script")
    parser.add_argument("mode", choices=("server", "client"), help="Run as server or client")
    parser.add_argument("protocol", choices=("tcp", "udp"), help="Use TCP or UDP")
    parser.add_argument("--ip", default="127.0.0.1", help="IP address to bind/connect to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port number to use")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="Message sent by the client")
    return parser.parse_args()


def run_server(protocol: str, ip: str, port: int) -> None:
    if protocol == "tcp":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((ip, port))
            server_socket.listen(1)
            print(f"TCP server listening on {ip}:{port}")

            client_socket, client_address = server_socket.accept()
            with client_socket:
                data = client_socket.recv(4096)
                message = data.decode("utf-8", errors="replace")
                print(f"Received from {client_address[0]}: {message}")
                client_socket.sendall(DEFAULT_RESPONSE.encode("utf-8"))
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
            server_socket.bind((ip, port))
            print(f"UDP server listening on {ip}:{port}")

            data, client_address = server_socket.recvfrom(4096)
            message = data.decode("utf-8", errors="replace")
            print(f"Received from {client_address[0]}: {message}")
            server_socket.sendto(DEFAULT_RESPONSE.encode("utf-8"), client_address)


def run_client(protocol: str, ip: str, port: int, message: str) -> None:
    payload = message.encode("utf-8")

    if protocol == "tcp":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((ip, port))
            client_socket.sendall(payload)
            response = client_socket.recv(4096).decode("utf-8", errors="replace")
            server_ip = client_socket.getpeername()[0]
            print(f"Received from {server_ip}: {response}")
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
            client_socket.sendto(payload, (ip, port))
            response, server_address = client_socket.recvfrom(4096)
            print(f"Received from {server_address[0]}: {response.decode('utf-8', errors='replace')}")


def main() -> None:
    args = parse_args()

    if args.mode == "server":
        run_server(args.protocol, args.ip, args.port)
    else:
        run_client(args.protocol, args.ip, args.port, args.message)


if __name__ == "__main__":
    main()