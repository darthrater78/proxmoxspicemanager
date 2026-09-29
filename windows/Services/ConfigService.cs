using System.Diagnostics;
using System.IO;
using System.Text.Json;
using ProxmoxSpiceManager.Models;

namespace ProxmoxSpiceManager.Services;

public static class ConfigService
{
    private static readonly string ConfigDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "proxmox-spice");

    private static readonly string ConfigFile = Path.Combine(ConfigDir, "connections.json");

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public static AppConfig Load()
    {
        if (!File.Exists(ConfigFile))
            return new AppConfig();

        try
        {
            var json = File.ReadAllText(ConfigFile);
            return JsonSerializer.Deserialize<AppConfig>(json, JsonOpts) ?? new AppConfig();
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[Config] Load failed: {ex.Message}");
            return new AppConfig();
        }
    }

    public static void Save(AppConfig config)
    {
        Directory.CreateDirectory(ConfigDir);
        var json = JsonSerializer.Serialize(config, JsonOpts);
        File.WriteAllText(ConfigFile, json);
    }

    public static string? GetSecret(ClusterConfig cluster)
    {
        if (string.IsNullOrEmpty(cluster.TokenSecretEnc))
            return null;
        return DpapiService.Decrypt(cluster.TokenSecretEnc);
    }

    public static void SaveSecret(ClusterConfig cluster, string secret)
    {
        cluster.TokenSecretEnc = DpapiService.Encrypt(secret);
    }

    // Every DPAPI blob starts with this header (version 1 + the DPAPI provider GUID), base64
    private const string DpapiPrefix = "AQAAANCMnd8BFdERjHoAwE/Cl+";

    // The secret in an imported cluster: token_secret (export files from 3.0.0 on, both apps),
    // else token_secret_enc, which is this user's DPAPI blob when re-importing a config file
    // and the plaintext secret in exports from the Windows app before 3.0.0. A DPAPI blob
    // from another user or machine can't be decrypted: null, and the secret must be re-entered.
    public static string? ImportedSecret(ClusterConfig cluster)
    {
        if (!string.IsNullOrEmpty(cluster.TokenSecret))
            return cluster.TokenSecret;
        var enc = cluster.TokenSecretEnc;
        if (string.IsNullOrEmpty(enc))
            return null;
        if (enc.StartsWith(DpapiPrefix, StringComparison.Ordinal))
            return OperatingSystem.IsWindows() ? DpapiService.Decrypt(enc) : null;
        return enc;
    }

    public static void DeleteSecret(ClusterConfig cluster)
    {
        cluster.TokenSecretEnc = null;
    }

    public static void MigrateSecrets(AppConfig config)
    {
        // The Python version stored plaintext "token_secret" — encrypted versions use "token_secret_enc"
        // This is handled by JSON deserialization; enc field is already mapped
    }
}
