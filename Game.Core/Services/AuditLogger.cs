using System;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Game.Core.Services;

/// <summary>
/// Writes deterministic security audit records to JSONL under logs/ci/&lt;date&gt;/security-audit.jsonl.
/// </summary>
public sealed class AuditLogger
{
    private const string FileName = "security-audit.jsonl";
    private static readonly UTF8Encoding Utf8WithoutBom = new(encoderShouldEmitUTF8Identifier: false);
    private readonly string repositoryRoot;
    private readonly Func<DateTimeOffset> utcNow;

    public AuditLogger(string repositoryRoot, Func<DateTimeOffset>? utcNow = null)
    {
        if (string.IsNullOrWhiteSpace(repositoryRoot))
        {
            throw new ArgumentException("Repository root must not be empty.", nameof(repositoryRoot));
        }

        this.repositoryRoot = Path.GetFullPath(repositoryRoot);
        this.utcNow = utcNow ?? (() => DateTimeOffset.UtcNow);
    }

    public string BuildRelativePath(DateTimeOffset timestampUtc)
    {
        var dateSegment = timestampUtc.ToUniversalTime().ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        return $"logs/ci/{dateSegment}/{FileName}";
    }

    public string BuildAbsolutePath(DateTimeOffset timestampUtc)
    {
        var relative = BuildRelativePath(timestampUtc).Replace('/', Path.DirectorySeparatorChar);
        return Path.Combine(this.repositoryRoot, relative);
    }

    public void RecordSave(string target, string caller, DateTimeOffset? timestampUtc = null)
    {
        Record("save", "ok", target, caller, timestampUtc);
    }

    public void RecordLoad(string target, string caller, DateTimeOffset? timestampUtc = null)
    {
        Record("load", "ok", target, caller, timestampUtc);
    }

    public void RecordOfferLock(string target, string caller, DateTimeOffset? timestampUtc = null)
    {
        Record("offer_lock", "ok", target, caller, timestampUtc);
    }

    public void RecordDeny(string reason, string target, string caller, DateTimeOffset? timestampUtc = null)
    {
        Record("deny", reason, target, caller, timestampUtc);
    }

    public void Record(string action, string reason, string target, string caller, DateTimeOffset? timestampUtc = null)
    {
        if (string.IsNullOrWhiteSpace(action))
        {
            throw new ArgumentException("Action must not be empty.", nameof(action));
        }

        if (string.IsNullOrWhiteSpace(reason))
        {
            throw new ArgumentException("Reason must not be empty.", nameof(reason));
        }

        if (string.IsNullOrWhiteSpace(target))
        {
            throw new ArgumentException("Target must not be empty.", nameof(target));
        }

        if (string.IsNullOrWhiteSpace(caller))
        {
            throw new ArgumentException("Caller must not be empty.", nameof(caller));
        }

        var ts = (timestampUtc ?? this.utcNow()).ToUniversalTime();
        var absolutePath = BuildAbsolutePath(ts);
        var parent = Path.GetDirectoryName(absolutePath);
        if (!string.IsNullOrWhiteSpace(parent))
        {
            Directory.CreateDirectory(parent);
        }

        var entry = new AuditLogRecord(
            Ts: ts.ToString("O", CultureInfo.InvariantCulture),
            Action: action,
            Reason: reason,
            Target: target,
            Caller: caller);

        var jsonLine = JsonSerializer.Serialize(entry);
        File.AppendAllText(absolutePath, jsonLine + Environment.NewLine, Utf8WithoutBom);
    }

    private sealed record AuditLogRecord(
        [property: JsonPropertyName("ts")] string Ts,
        [property: JsonPropertyName("action")] string Action,
        [property: JsonPropertyName("reason")] string Reason,
        [property: JsonPropertyName("target")] string Target,
        [property: JsonPropertyName("caller")] string Caller);
}
