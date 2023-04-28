#!/usr/bin/env python3

import argparse
import asyncio
import logging


class Client:
    """The client to the real upstream Redis server.

    It handles the Redis authentication on behalf of the client connecting to
    the proxy.
    """

    def __init__(self, reader, writer):
        self.logger = logging.getLogger("client")

        self.peer_reader = reader
        self.peer_writer = writer

    async def authenticate(self, password, reader, writer):
        """Sends the Redis authentication command to upstream"""

        self.logger.debug("Try to authenticate to upstream")
        writer.write(f"AUTH {password}\r\n".encode("utf-8"))
        await writer.drain()

        results = await reader.read(1024)

        if results != b"+OK\r\n":
            # TODO: this closes the connection, but the upstream implementation waits for a new password.
            # What should we do here?
            self.peer_writer.write(b"-WRONGPASS unable to auto-authenticate\r\n")
            await self.peer_writer.drain()
            raise RuntimeError(f"Authentication failed: {results}")
        else:
            self.logger.debug("Successfully authenticated to upstream!")

    async def connect(self, hostname, port, password):
        self.logger.info(f"Connecting to {hostname}:{port}")
        reader, writer = await asyncio.open_connection(hostname, port)

        # Try to authenticate with upstream.
        # This may fail if we don't have the right password loaded.
        await self.authenticate(password, reader, writer)

        # Connect the client to our proxy to the upstream server.
        c2s = Pipe(self.peer_reader, writer, ">>")
        s2c = Pipe(reader, self.peer_writer, "<<")

        tasks = [
            asyncio.create_task(s2c.flow(), name="s2c"),
            asyncio.create_task(c2s.flow(), name="c2s"),
        ]

        # As soon as one side of the connection closes the connection ...
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # ... cancel all the rest.
        for task in pending:
            task.cancel()

        await asyncio.gather(*pending)

        self.logger.info(f"Closing connection to {hostname}:{port}")
        writer.close()
        await writer.wait_closed()


class Pipe:
    """Sends the data from a StreamReader to a StreamWriter"""

    def __init__(self, reader, writer, direction):
        self.reader = reader
        self.writer = writer
        self.logger = logging.getLogger(f"pipe {direction}")

    async def flow(self):
        """Read from the StreamReader and sends to the StreamWriter"""

        try:
            while not self.reader.at_eof():
                data = await self.reader.read(2**16)
                if data == b"":
                    self.logger.debug("EOF")
                    return

                # Pipe the data we just read to the other side
                self.logger.info("data=%s", data)
                self.writer.write(data)
                await self.writer.drain()

        finally:
            self.writer.close()
            await self.writer.wait_closed()


class Server:
    """The server on which clients are connecting

    This provides the "public" interface for other Redis clients to connect on.
    """

    def __init__(self, client_factory):
        self.logger = logging.getLogger("server")
        self.client_factory = client_factory

    async def serve_forever(self, hostname="127.0.0.1", port=6378):
        server = await asyncio.start_server(self.handle_server, hostname, port)
        async with server:
            await server.serve_forever()

    async def handle_server(self, reader, writer):
        """Handle the connection from a single Redis client"""

        client = self.client_factory.connect(reader, writer)
        try:
            await client
        except Exception as exc:
            self.logger.critical("Connection to upstream failed: %s", exc)

        writer.close()
        await writer.wait_closed()


class UpstreamClientFactory:
    """Wraps the upstream Redis server parameters and initiate the connection."""

    def __init__(self, hostname, port, password):
        self.hostname = hostname
        self.port = port
        self.password = password
        self.logger = logging.getLogger("client-factory")

    def connect(self, reader, writer):
        """Connect to the upstream Redis server and connects the client to upstream"""

        client = Client(reader, writer)
        self.logger.info(f"connecting to upstream {self.hostname}:{self.port}")
        return client.connect(self.hostname, self.port, self.password)


async def main(args):
    # Our client to connect to the upstream (real) Redis server
    client_factory = UpstreamClientFactory(
        args.upstream_address, args.upstream_port, args.upstream_password
    )

    # Our main fake Redis server on which the other Redis clients will connect on.
    server = Server(client_factory)
    await server.serve_forever(args.listen_address, args.listen_port)


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--upstream-address", help="The upstream Redis instance address to connect on"
    )
    parser.add_argument(
        "--upstream-password", help="The upstream Redis instance password to authenticate with"
    )
    parser.add_argument(
        "--upstream-port",
        type=int,
        default=6379,
        help="The upstream Redis instance port to connect on",
    )

    parser.add_argument(
        "--listen-address",
        default="127.0.0.1",
        help="The address to listen for connections on",
    )
    parser.add_argument(
        "--listen-port", default="6379", help="The port to listen for connections on"
    )

    parser.add_argument(
        "-v",
        action="append_const",
        dest="verbosity",
        const=-10,
        default=[logging.ERROR],
        help="Increase verbosity. Can be passed multiple times.",
    )

    args = parser.parse_args()

    level = sum(args.verbosity)
    logging.basicConfig(level=level)
    try:
        asyncio.run(main(args), debug=True)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    cli()
