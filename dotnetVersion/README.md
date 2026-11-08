# FO3 server in .NET 10 (in progress)

The Python server moves here one piece at a time. Phase 1 (this) puts a .NET host in front of
it: the host owns `https://APSEODESK172:443` and the messenger, and forwards every game request
it does not handle itself (for now, all of them) to the Python server. Endpoints then move over
one by one, each checked against what Python answered for the same request.

```
fifazf.exe ──https :443──> FO3.Host ──http 127.0.0.1:18080──> http_config.py (+ admin :8088)
           ──tcp :28002──> FO3.Host messenger  <──udp :28003── http_config.py pushes
```

## Run

From the repository root, after the setup in `docs/3sea-client.md` and with the .NET 10 SDK:

    play_dotnet.bat

It builds the host, starts `http_config.py 18080` (bound to 127.0.0.1) and the host, then the
game. `play.bat` still runs the Python server alone.

While it runs, `https://127.0.0.1/_fo3/fallbacks` (loopback only) lists the requests the
client made that nobody implements yet (Python answered them with its generic fallback), by
count. With `--Fo3:Golden:RecordDir=<folder>` every request and its answer is also written to
`<folder>/golden-YYYYMMDD.jsonl`: the material for the golden tests of later phases.

Settings are in `src/FO3.Host/appsettings.json` (`Fo3` section), or on the command line
(`--Fo3:Https:Bind=127.0.0.2`) or as environment variables (`Fo3__Https__Bind`). Relative paths
are under the repository (`certs/server.pem`, `gamedata/state.json`).

## Layout

| Project | What |
|---|---|
| `src/FO3.Domain` | Game rules without I/O. `Randomness/PyRandom.cs`: CPython's `random.Random`, bit for bit |
| `src/FO3.Application` | Use cases and the ports they need (`IGameStateStore`, `IClock`) |
| `src/FO3.Infrastructure` | `JsonFileStateStore` (Python's `state.json`, written as Python writes it), `PyJson` (`json.dumps` text) |
| `src/FO3.Host` | Kestrel TLS, the YARP forward to Python, the fallback counter, the golden recorder, the messenger |
| `tests/*` | xUnit; `Golden/*.json` are made by the Python code itself |

## Tests

    dotnet test FO3.slnx

The golden files come from the Python server's own functions; regenerate them after a change on
the Python side:

    python dotnetVersion/tools/golden/gen_pyrandom_golden.py
    python dotnetVersion/tools/golden/gen_host_golden.py

`gen_pyrandom_golden.py` covers the seeded draws the server makes (virtual managers, their Rank
games, AI clubs, club points, market prices) and needs no card database.
