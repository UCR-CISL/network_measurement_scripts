#!/usr/bin/env python3
"""Simple FTP-like file transfer tool.

Server mode: listens for file requests and serves files from a directory.
Client mode: connects to a server and downloads files.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path


DEFAULT_PORT = 9999
DEFAULT_IP = "127.0.0.1"
BUFFER_SIZE = 8192


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple FTP-like file transfer")
    parser.add_argument("mode", choices=("server", "client"), help="Run as server or client")
    parser.add_argument("--ip", default=DEFAULT_IP, help="IP address to bind/connect to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port number to use")
    
    # Server-specific arguments
    parser.add_argument("--path", help="Server: directory path to serve files from")
    
    # Client-specific arguments
    parser.add_argument("--file", help="Client: filename to download from server")
    parser.add_argument("--output", help="Client: local output path (default: same as filename)")
    
    return parser.parse_args()


def run_server(ip: str, port: int, serve_path: str) -> None:
    """Server: listen for file requests and send file contents."""
    serve_dir = Path(serve_path).resolve()
    
    if not serve_dir.is_dir():
        print(f"Error: {serve_path} is not a directory", file=sys.stderr)
        return
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((ip, port))
        server_socket.listen(1)
        print(f"FTP server listening on {ip}:{port}, serving from {serve_dir}")

        while True:
            try:
                client_socket, client_address = server_socket.accept()
            except KeyboardInterrupt:
                print("\nServer shutting down")
                break

            with client_socket:
                print(f"Client connected from {client_address[0]}")
                
                # Receive file request
                request_data = client_socket.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
                filename = request_data.strip()
                
                # Validate and serve file
                file_path = (serve_dir / filename).resolve()
                
                # Security check: ensure path is within serve_dir
                try:
                    file_path.relative_to(serve_dir)
                except ValueError:
                    print(f"  Rejected: path traversal attempt: {filename}")
                    client_socket.sendall(b"ERROR: path traversal not allowed\n")
                    continue
                
                if not file_path.exists():
                    print(f"  Requested file not found: {filename}")
                    client_socket.sendall(b"ERROR: file not found\n")
                    continue
                
                if not file_path.is_file():
                    print(f"  Requested path is not a file: {filename}")
                    client_socket.sendall(b"ERROR: not a file\n")
                    continue
                
                # Send file size followed by content
                file_size = file_path.stat().st_size
                header = f"OK {file_size}\n".encode("utf-8")
                client_socket.sendall(header)
                
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(BUFFER_SIZE)
                        if not chunk:
                            break
                        client_socket.sendall(chunk)
                
                print(f"  Sent {filename} ({file_size} bytes)")


def run_client(ip: str, port: int, filename: str, output_path: str | None) -> None:
    """Client: request a file from server and save it locally."""
    if output_path is None:
        output_path = filename
    
    output_file = Path(output_path)
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        print(f"Connecting to {ip}:{port}")
        client_socket.connect((ip, port))
        
        # Send file request
        request = f"{filename}\n".encode("utf-8")
        client_socket.sendall(request)
        print(f"Requesting file: {filename}")
        
        # Receive response header
        header_data = b""
        while b"\n" not in header_data:
            chunk = client_socket.recv(BUFFER_SIZE)
            if not chunk:
                print("Error: connection closed by server", file=sys.stderr)
                return
            header_data += chunk
        
        header_line = header_data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
        
        if header_line.startswith("ERROR"):
            print(f"Server error: {header_line}", file=sys.stderr)
            return
        
        if not header_line.startswith("OK"):
            print(f"Invalid server response: {header_line}", file=sys.stderr)
            return
        
        # Parse file size
        try:
            _, size_str = header_line.split(maxsplit=1)
            file_size = int(size_str)
        except (ValueError, IndexError):
            print(f"Invalid response format: {header_line}", file=sys.stderr)
            return
        
        # Receive file content
        print(f"Downloading {file_size} bytes to {output_path}")
        bytes_received = 0
        
        with open(output_file, "wb") as f:
            # Write any data after header that was already received
            remaining_header = header_data.split(b"\n", 1)
            if len(remaining_header) > 1:
                f.write(remaining_header[1])
                bytes_received += len(remaining_header[1])
            
            while bytes_received < file_size:
                chunk_size = min(BUFFER_SIZE, file_size - bytes_received)
                chunk = client_socket.recv(chunk_size)
                if not chunk:
                    print(f"Error: connection closed after {bytes_received} bytes", file=sys.stderr)
                    return
                f.write(chunk)
                bytes_received += len(chunk)
        
        print(f"Download complete: {output_path} ({bytes_received} bytes)")


def main() -> None:
    args = parse_args()
    
    if args.mode == "server":
        if not args.path:
            print("Error: --path is required for server mode", file=sys.stderr)
            sys.exit(1)
        run_server(args.ip, args.port, args.path)
    else:
        if not args.file:
            print("Error: --file is required for client mode", file=sys.stderr)
            sys.exit(1)
        run_client(args.ip, args.port, args.file, args.output)


if __name__ == "__main__":
    main()
