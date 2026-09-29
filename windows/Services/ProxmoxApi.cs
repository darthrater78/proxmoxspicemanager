using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace ProxmoxSpiceManager.Services;

public class AuthInfo
{
    public string? TokenId { get; set; }
    public string? TokenSecret { get; set; }
    public string? Ticket { get; set; }
    public string? Csrf { get; set; }
    public string? TlsFingerprint { get; set; }
    public DateTime Issued { get; set; } = DateTime.UtcNow;  // when the ticket was issued
}

public class ProxmoxApi
{
    // One client per pin ("" = the system's CAs decide). The certificate is checked in
    // the TLS handshake, before a request, token or password is sent.
    private static readonly ConcurrentDictionary<string, HttpClient> Clients = new();
    // Certificates refused per host ("https://host:port"), for the trust prompt
    private static readonly ConcurrentDictionary<string, (string Fingerprint, bool Changed)> TlsFailures = new();

    public static string Fingerprint(X509Certificate2 cert) =>
        string.Join(":", SHA256.HashData(cert.RawData).Select(b => b.ToString("X2")));

    private static HttpClient ClientFor(string? pin) => Clients.GetOrAdd(pin ?? "", p =>
        new HttpClient(new HttpClientHandler
        {
            ServerCertificateCustomValidationCallback = (request, cert, _, errors) =>
            {
                if (cert == null) return false;
                var seen = Fingerprint(cert);
                // A pin replaces CA and hostname checks: only that exact certificate passes
                var ok = p.Length > 0 ? seen == p : errors == SslPolicyErrors.None;
                if (!ok && request.RequestUri != null)
                    TlsFailures[request.RequestUri.GetLeftPart(UriPartial.Authority)] = (seen, p.Length > 0);
                return ok;
            }
        }) { Timeout = Timeout.InfiniteTimeSpan });

    // The certificate the last failed request to this host refused, if that is why it failed
    public static (string Fingerprint, bool Changed)? TakeTlsFailure(string host) =>
        Uri.TryCreate(host, UriKind.Absolute, out var uri) &&
        TlsFailures.TryRemove(uri.GetLeftPart(UriPartial.Authority), out var failure) ? failure : null;

    public static async Task<JsonElement?> RequestAsync(
        string host, string endpoint, string method = "GET",
        AuthInfo? auth = null, string? postData = null,
        TimeSpan? timeout = null)
    {
        if (!host.StartsWith("https://"))
            return null;

        var client = ClientFor(auth?.TlsFingerprint);

        var request = new HttpRequestMessage(new HttpMethod(method), $"{host}{endpoint}");

        if (auth?.TokenId != null && auth.TokenSecret != null)
        {
            request.Headers.Authorization = new AuthenticationHeaderValue(
                "PVEAPIToken", $"{auth.TokenId}={auth.TokenSecret}");
        }
        else if (auth?.Ticket != null)
        {
            request.Headers.Add("Cookie", $"PVEAuthCookie={auth.Ticket}");
            if (auth.Csrf != null)
                request.Headers.Add("CSRFPreventionToken", auth.Csrf);
        }

        if (method is "POST" or "DELETE" or "PUT")
        {
            request.Content = postData != null
                ? new StringContent(postData, Encoding.UTF8, "application/x-www-form-urlencoded")
                : new StringContent("", Encoding.UTF8, "application/x-www-form-urlencoded");
        }

        using var cts = new CancellationTokenSource(timeout ?? TimeSpan.FromSeconds(15));
        var sw = Stopwatch.StartNew();
        try
        {
            DebugLogger.Log($"[API] {method} {endpoint}");
            var response = await client.SendAsync(request, cts.Token);
            var body = await response.Content.ReadAsStringAsync();
            sw.Stop();
            var statusCode = (int)response.StatusCode;
            DebugLogger.Log($"[API] {method} {endpoint} -> {statusCode} ({sw.ElapsedMilliseconds}ms, {body.Length} chars)");
            if (!response.IsSuccessStatusCode)
            {
                DebugLogger.Log($"[API] {method} {endpoint} returned {statusCode} ({body.Length} chars)");
                return null;
            }
            return JsonSerializer.Deserialize<JsonElement>(body);
        }
        catch (Exception ex)
        {
            sw.Stop();
            DebugLogger.Log($"[API] {method} {endpoint} FAILED after {sw.ElapsedMilliseconds}ms: {ex.GetType().Name}: {ex.Message}");
            System.Diagnostics.Debug.WriteLine($"[ProxmoxApi] {method} {endpoint} failed: {ex.Message}");
            return null;
        }
    }

    // Wait for the task a POST started (its "data" is the task's UPID): null once it ended
    // well, else why not. Proxmox runs start, shutdown, snapshots etc. as background tasks,
    // so the POST returns before the work is done.
    public static async Task<string?> WaitForTaskAsync(string host, AuthInfo? auth, JsonElement? started,
        TimeSpan? timeout = null)
    {
        if (started?.TryGetProperty("data", out var data) != true || data.ValueKind != JsonValueKind.String ||
            data.GetString() is not { } upid || !upid.StartsWith("UPID:"))
            return null;  // nothing to wait for
        var node = upid.Split(':')[1];
        var path = $"/api2/json/nodes/{Uri.EscapeDataString(node)}/tasks/{Uri.EscapeDataString(upid)}/status";
        var deadline = DateTime.UtcNow + (timeout ?? TimeSpan.FromMinutes(3));
        while (DateTime.UtcNow < deadline)
        {
            var status = await RequestAsync(host, path, auth: auth);
            if (status?.TryGetProperty("data", out var task) == true &&
                task.TryGetProperty("status", out var state) && state.GetString() == "stopped")
            {
                var exit = task.TryGetProperty("exitstatus", out var e) ? e.GetString() ?? "" : "";
                return exit == "OK" || exit.StartsWith("WARNINGS") ? null : exit.Length > 0 ? exit : "task failed";
            }
            await Task.Delay(1000);
        }
        return "still running after 3 minutes";
    }

    public static async Task<AuthInfo?> AuthenticatePasswordAsync(
        string host, string username, string password, string? pin = null)
    {
        // Never send a password over plain HTTP (an imported config can bypass
        // the check in ClusterDialog).
        if (!host.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            return null;

        var client = ClientFor(pin);

        var content = new FormUrlEncodedContent(new Dictionary<string, string>
        {
            ["username"] = username,
            ["password"] = password,
        });

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var sw = Stopwatch.StartNew();
        try
        {
            DebugLogger.Log($"[API] POST /api2/json/access/ticket (password auth for {username})");
            var response = await client.PostAsync($"{host}/api2/json/access/ticket", content, cts.Token);
            var body = await response.Content.ReadAsStringAsync();
            sw.Stop();
            DebugLogger.Log($"[API] Password auth -> {(int)response.StatusCode} ({sw.ElapsedMilliseconds}ms)");
            var json = JsonSerializer.Deserialize<JsonElement>(body);

            if (json.TryGetProperty("data", out var data) &&
                data.TryGetProperty("ticket", out var ticket))
            {
                DebugLogger.Log("[API] Password auth succeeded — ticket obtained");
                return new AuthInfo
                {
                    Ticket = ticket.GetString(),
                    Csrf = data.TryGetProperty("CSRFPreventionToken", out var csrf)
                        ? csrf.GetString() : null,
                    TlsFingerprint = pin,
                };
            }
            DebugLogger.Log("[API] Password auth failed — no ticket in response");
        }
        catch (Exception ex)
        {
            sw.Stop();
            DebugLogger.Log($"[API] Password auth FAILED after {sw.ElapsedMilliseconds}ms: {ex.GetType().Name}: {ex.Message}");
            System.Diagnostics.Debug.WriteLine($"[ProxmoxApi] Auth failed: {ex.Message}");
        }
        return null;
    }
}
