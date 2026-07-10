using System.Net;
using System.Net.Http;
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
    public bool SkipTlsVerify { get; set; }
}

public class ProxmoxApi
{
    private static HttpClient CreateClient(bool skipTls)
    {
        if (skipTls)
        {
            var handler = new HttpClientHandler
            {
                ServerCertificateCustomValidationCallback = (_, _, _, _) => true
            };
            return new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(15) };
        }
        return new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
    }

    public static async Task<JsonElement?> RequestAsync(
        string host, string endpoint, string method = "GET",
        AuthInfo? auth = null, string? postData = null)
    {
        if (!host.StartsWith("https://"))
            return null;

        bool skipTls = auth?.SkipTlsVerify ?? false;
        using var client = CreateClient(skipTls);

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

        try
        {
            var response = await client.SendAsync(request);
            var body = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<JsonElement>(body);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[ProxmoxApi] {method} {endpoint} failed: {ex.Message}");
            return null;
        }
    }

    public static async Task<AuthInfo?> AuthenticatePasswordAsync(
        string host, string username, string password, bool skipTls = false)
    {
        using var client = CreateClient(skipTls);

        var content = new FormUrlEncodedContent(new Dictionary<string, string>
        {
            ["username"] = username,
            ["password"] = password,
        });

        try
        {
            var response = await client.PostAsync($"{host}/api2/json/access/ticket", content);
            var body = await response.Content.ReadAsStringAsync();
            var json = JsonSerializer.Deserialize<JsonElement>(body);

            if (json.TryGetProperty("data", out var data) &&
                data.TryGetProperty("ticket", out var ticket))
            {
                return new AuthInfo
                {
                    Ticket = ticket.GetString(),
                    Csrf = data.TryGetProperty("CSRFPreventionToken", out var csrf)
                        ? csrf.GetString() : null,
                    SkipTlsVerify = skipTls,
                };
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[ProxmoxApi] Auth failed: {ex.Message}");
        }
        return null;
    }
}
