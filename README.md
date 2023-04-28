# Redis proxy

A Redis proxy that handles authentication to Redis, on behalf of its clients.

When it starts, the proxy listen for connections from your favorite Redis client.

Each time a Redis client on the proxy, the proxy connects back on an upstream
Redis server and:

1. Authenticate on the Redis server, using the [Redis `AUTH` command](https://redis.io/docs/management/security/#authentication)
2. If the authentication succeeds, the connection to the Redis server is
   handed over to the client of the proxy:
   * All the commands from the client are forwarded to the upstream server, as
     if the client was directly connected to the server.
   * Similarly, all the responses from upstream are sent back to the client.
3. If the authentication fails, then the proxy gives up and closes the
   connection to the client.

```
Client -> [Redis Proxy] -> Upstream Redis server
```

## Demo

1. Start a Redis server instance, protected by a password. Use:

   ```sh
   redis-server --port 6379 --requirepass secret-password
   ```

   Or the Docker command:

   ```sh
   docker run --rm --port 6379:6379 redis --requirepass secret-password
   ```

   For convenience, a Docker Compose also exists:

   ```sh
   docker compose up
   ```

   This will create a new Redis server running on port 6379.

2. Start the proxy with:

   ```sh
   ./redis-proxy.py -vv --listen-port 6378 --upstream-address 127.0.0.1 --upstream-port 6379 --upstream-password secret-password
   ```

   This will create a Redis-compatible server running on TCP port 6378.

3. Start any Redis client and connect it on `127.0.0.1` port 6378 (the proxy), **without any password**:

   ```sh
   $ redis-cli -h 127.0.0.1 -p 6378 ping
   PONG
   $ redis-cli -h 127.0.0.1 -p 6379 ping
   (error) NOAUTH Authentication required.
   $ redis-cli -h 127.0.0.1 -p 6379 --pass secret-password ping
   PONG
   ```


## Requirements

This is a pure Python 3 project. It requires Python 3.8 or greater.


## Status

The proxy works 🎉

It super slow 🎉 [redis-benchmark](https://redis.io/docs/management/optimization/benchmarks/) is about 100 slower when going through the proxy, compared to going directly to the upstream Redis server :)
