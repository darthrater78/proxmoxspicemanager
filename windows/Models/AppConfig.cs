using System.Text.Json.Serialization;

namespace ProxmoxSpiceManager.Models;

public class AppConfig
{
    [JsonPropertyName("version")]
    public string Version { get; set; } = "1.0.0";

    [JsonPropertyName("clusters")]
    public List<ClusterConfig> Clusters { get; set; } = [];

    [JsonPropertyName("theme")]
    public string Theme { get; set; } = "Catppuccin Mocha";

    [JsonPropertyName("accent")]
    public string Accent { get; set; } = Themes.DefaultAccent;

    [JsonPropertyName("group_by_node")]
    public bool GroupByNode { get; set; } = true;

    // Sort key shared with the Linux app: name, vmid, ip, node, pool, snaps, status, notes
    [JsonPropertyName("vm_sort")]
    public string VmSort { get; set; } = "vmid";

    [JsonPropertyName("vm_sort_desc")]
    public bool VmSortDesc { get; set; }

    // Shared with the Linux app; IPv6 addresses stay hidden unless it's on
    [JsonPropertyName("show_ipv6")]
    public bool ShowIpv6 { get; set; }

    [JsonPropertyName("column_order")]
    public List<string>? ColumnOrder { get; set; }

    [JsonPropertyName("prereqs_ok")]
    public bool PrereqsOk { get; set; }

    [JsonPropertyName("note_options")]
    public List<string>? NoteOptions { get; set; }

    [JsonPropertyName("vm_notes")]
    public Dictionary<string, string>? VmNotes { get; set; }

    [JsonPropertyName("debug_logging")]
    public bool DebugLogging { get; set; }
}

public class ClusterConfig
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("host")]
    public string Host { get; set; } = "";

    [JsonPropertyName("auth_method")]
    public string AuthMethod { get; set; } = "token";

    [JsonPropertyName("token_id")]
    public string TokenId { get; set; } = "";

    [JsonPropertyName("username")]
    public string Username { get; set; } = "root@pam";

    // SHA-256 of the self-signed certificate the user confirmed for this host ("AB:CD:…");
    // null means the system's CAs decide. Replaces the old skip_tls_verify.
    [JsonPropertyName("tls_fingerprint")]
    public string? TlsFingerprint { get; set; }

    [JsonPropertyName("token_secret_enc")]
    public string? TokenSecretEnc { get; set; }

    // Plaintext secret, only in export files (the format both apps read). Import moves it
    // into TokenSecretEnc, so it is never saved to connections.json.
    [JsonPropertyName("token_secret")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TokenSecret { get; set; }
}
