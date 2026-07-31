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

    [JsonPropertyName("skip_tls_verify")]
    public bool SkipTlsVerify { get; set; }

    [JsonPropertyName("token_secret_enc")]
    public string? TokenSecretEnc { get; set; }
}
