using System.Collections.Concurrent;

namespace FO3.Host.Proxy;

/// <summary>
/// The client requests nobody implements yet: the Python server answers them with its generic
/// fallback ({} or {"result": true}) and the header X-FO3-Fallback. Counted by method and path,
/// this is the live list of the stale endpoints real play reaches (the Launcher's Monitor reads it).
/// </summary>
public sealed class FallbackMonitor
{
    public const string Header = "X-FO3-Fallback";

    public sealed record Hit(string Method, string Path, long Count, DateTimeOffset First, DateTimeOffset Last);

    private readonly ConcurrentDictionary<(string, string), Hit> _hits = new();

    public void Record(string method, string path, DateTimeOffset at) =>
        _hits.AddOrUpdate((method, path), _ => new Hit(method, path, 1, at, at),
            (_, h) => h with { Count = h.Count + 1, Last = at });

    public IReadOnlyList<Hit> Snapshot() =>
        _hits.Values.OrderByDescending(h => h.Count).ThenBy(h => h.Path, StringComparer.Ordinal).ToList();
}
