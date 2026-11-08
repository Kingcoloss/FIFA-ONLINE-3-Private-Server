namespace FO3.Host;

/// <summary>appsettings.json "Fo3" (environment: Fo3__Https__Bind=127.0.0.2 and so on).</summary>
public sealed class Fo3Options
{
    public HttpsOptions Https { get; set; } = new();
    public BackendOptions Backend { get; set; } = new();
    public MessengerOptions Messenger { get; set; } = new();
    public GoldenOptions Golden { get; set; } = new();
    /// <summary>The Python server's state file; a relative path is under the repository.</summary>
    public string StatePath { get; set; } = "gamedata/state.json";

    public sealed class HttpsOptions
    {
        /// <summary>The address 443 is bound on; 127.0.0.2 with a hosts entry keeps clear of another program.</summary>
        public string Bind { get; set; } = "0.0.0.0";
        /// <summary>fifazf.exe calls https://APSEODESK172 on 443; only tests use another port.</summary>
        public int Port { get; set; } = 443;
        /// <summary>The PEM with the certificate and its key (the Python server's certs/server.pem; relative = under the repository).</summary>
        public string CertPem { get; set; } = "certs/server.pem";
        /// <summary>false: plain http (tests).</summary>
        public bool Enabled { get; set; } = true;
    }

    public sealed class BackendOptions
    {
        /// <summary>The Python server, started as `http_config.py 18080` (plain http, loopback).</summary>
        public string Url { get; set; } = "http://127.0.0.1:18080/";
    }

    public sealed class MessengerOptions
    {
        /// <summary>false: messenger.py runs instead.</summary>
        public bool Enabled { get; set; } = true;
        public string Bind { get; set; } = "0.0.0.0";
        public int Port { get; set; } = 28002;
        /// <summary>The UDP port the game server pushes to; default Port + 1 (fo3conf.MESSENGER_PUSH_PORT).</summary>
        public int? PushPort { get; set; }
    }

    public sealed class GoldenOptions
    {
        /// <summary>A folder: every request and its answer is appended there as one JSON line. Empty: off.</summary>
        public string RecordDir { get; set; } = "";
        /// <summary>Bodies longer than this are kept as their length and hash only.</summary>
        public int MaxBodyBytes { get; set; } = 256 * 1024;
    }
}
