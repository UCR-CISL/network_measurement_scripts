#!/usr/bin/env python3
"""RTT measurement tool for TCP or UDP.

Client mode sends timestamped probes for a fixed duration, waits for echoes,
prints each RTT, and writes results to CSV.

Server mode receives probes, prints the sender and probe payload, and echoes
the same payload back to the client.
"""

from __future__ import annotations

import argparse
import csv
import socket
import time
from pathlib import Path


DEFAULT_PORT = 9999
DEFAULT_DURATION = 10.0
DEFAULT_INTERVAL = 1.0
DEFAULT_TIMEOUT = 1.0
DEFAULT_CSV = "rtt_results.csv"
BUFFER_SIZE = 4096


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure round-trip time over TCP or UDP")
    parser.add_argument("mode", choices=("server", "client"), help="Run as server or client")
    parser.add_argument("protocol", choices=("tcp", "udp"), help="Use TCP or UDP")
    parser.add_argument("--ip", default="127.0.0.1", help="IP address to bind/connect to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port number to use")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="Total testing duration in seconds")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Delay between probes in seconds")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-probe receive timeout in seconds")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="CSV file path for client results")
    return parser.parse_args()


def build_probe(sequence: int, send_time_ns: int) -> str:
    return f"{sequence},{send_time_ns}\n"


def parse_probe(payload: str) -> tuple[int, int]:
    sequence_text, send_time_text = payload.strip().split(",", 1)
    return int(sequence_text), int(send_time_text)


def run_server(protocol: str, ip: str, port: int, duration: float) -> None:
    deadline = time.monotonic() + duration

    if protocol == "tcp":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((ip, port))
            server_socket.listen(1)
            server_socket.settimeout(1.0)
            print(f"TCP RTT server listening on {ip}:{port}")

            connection = None
            while time.monotonic() < deadline and connection is None:
                try:
                    connection, client_address = server_socket.accept()
                except socket.timeout:
                    continue

            if connection is None:
                return

            with connection:
                connection.settimeout(1.0)
                with connection.makefile("rwb") as stream:
                    while time.monotonic() < deadline:
                        try:
                            line = stream.readline()
                        except socket.timeout:
                            continue

                        if not line:
                            break

                        payload = line.decode("utf-8", errors="replace")
                        sequence, send_time_ns = parse_probe(payload)
                        print(f"Received from {client_address[0]} seq={sequence} send_time_ns={send_time_ns}")
                        stream.write(line)
                        stream.flush()
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
            server_socket.bind((ip, port))
            server_socket.settimeout(1.0)
            print(f"UDP RTT server listening on {ip}:{port}")

            while time.monotonic() < deadline:
                try:
                    data, client_address = server_socket.recvfrom(BUFFER_SIZE)
                except socket.timeout:
                    continue

                payload = data.decode("utf-8", errors="replace")
                sequence, send_time_ns = parse_probe(payload)
                print(f"Received from {client_address[0]} seq={sequence} send_time_ns={send_time_ns}")
                server_socket.sendto(data, client_address)


def write_csv_header(csv_path: Path) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([
            "sequence",
            "send_time_ns",
            "receive_time_ns",
            "rtt_ms",
            "status",
            "protocol",
            "server_ip",
            "server_port",
            "packets_sent",
            "packets_received",
            "packet_loss_percent",
        ])


def append_csv_row(csv_path: Path, row: list[object]) -> None:
    with csv_path.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(row)


def run_client(protocol: str, ip: str, port: int, duration: float, interval: float, timeout: float, csv_path_text: str) -> None:
    csv_path = Path(csv_path_text)
    write_csv_header(csv_path)

    deadline = time.monotonic() + duration
    sequence = 0
    packets_sent = 0
    packets_received = 0

    if protocol == "tcp":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((ip, port))
            client_socket.settimeout(timeout)

            with client_socket.makefile("rwb") as stream:
                while time.monotonic() < deadline:
                    send_time_ns = time.time_ns()
                    probe = build_probe(sequence, send_time_ns).encode("utf-8")
                    stream.write(probe)
                    stream.flush()
                    packets_sent += 1

                    try:
                        response = stream.readline()
                    except socket.timeout:
                        append_csv_row(csv_path, [sequence, send_time_ns, "", "", "timeout", protocol, ip, port, packets_sent, packets_received, ""])
                        print(f"seq={sequence} timeout")
                    else:
                        if not response:
                            append_csv_row(csv_path, [sequence, send_time_ns, "", "", "disconnected", protocol, ip, port, packets_sent, packets_received, ""])
                            print(f"seq={sequence} disconnected")
                            break

                        packets_received += 1
                        receive_time_ns = time.time_ns()
                        rtt_ms = (receive_time_ns - send_time_ns) / 1_000_000
                        response_text = response.decode("utf-8", errors="replace").strip()
                        append_csv_row(csv_path, [sequence, send_time_ns, receive_time_ns, f"{rtt_ms:.3f}", "ok", protocol, ip, port, packets_sent, packets_received, ""])
                        print(f"seq={sequence} from {client_socket.getpeername()[0]} rtt={rtt_ms:.3f} ms reply={response_text}")

                    sequence += 1
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(interval, remaining))
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
            client_socket.settimeout(timeout)

            while time.monotonic() < deadline:
                send_time_ns = time.time_ns()
                probe = build_probe(sequence, send_time_ns).encode("utf-8")
                client_socket.sendto(probe, (ip, port))
                packets_sent += 1

                try:
                    response, server_address = client_socket.recvfrom(BUFFER_SIZE)
                except socket.timeout:
                    append_csv_row(csv_path, [sequence, send_time_ns, "", "", "timeout", protocol, ip, port, packets_sent, packets_received, ""])
                    print(f"seq={sequence} timeout")
                else:
                    packets_received += 1
                    receive_time_ns = time.time_ns()
                    rtt_ms = (receive_time_ns - send_time_ns) / 1_000_000
                    response_text = response.decode("utf-8", errors="replace").strip()
                    append_csv_row(csv_path, [sequence, send_time_ns, receive_time_ns, f"{rtt_ms:.3f}", "ok", protocol, server_address[0], server_address[1], packets_sent, packets_received, ""])
                    print(f"seq={sequence} from {server_address[0]} rtt={rtt_ms:.3f} ms reply={response_text}")

                sequence += 1
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(interval, remaining))

    packet_loss_percent = 0.0 if packets_sent == 0 else ((packets_sent - packets_received) / packets_sent) * 100.0
    append_csv_row(csv_path, ["summary", "", "", "", "summary", protocol, ip, port, packets_sent, packets_received, f"{packet_loss_percent:.2f}"])
    print(
        f"summary: sent={packets_sent} received={packets_received} "
        f"loss={packet_loss_percent:.2f}%"
    )


def main() -> None:
    args = parse_args()

    if args.mode == "server":
        run_server(args.protocol, args.ip, args.port, args.duration)
    else:
        run_client(args.protocol, args.ip, args.port, args.duration, args.interval, args.timeout, args.csv)


if __name__ == "__main__":
    main()