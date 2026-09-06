using System;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task56AuditLogValidationTests
{
    // ACC:T56.8
    [Fact]
    public void ShouldReturnTrue_WhenAuditJsonlLineContainsAllRequiredFields()
    {
        var line = "{\"ts\":\"2026-03-10T12:00:00Z\",\"action\":\"url.deny\",\"reason\":\"offline_mode\",\"target\":\"https://example.com\",\"caller\":\"Security.OpenExternalUrl\"}";

        var isValid = HasRequiredAuditFields(line);

        isValid.Should().BeTrue();
    }

    [Fact]
    public void ShouldReturnFalse_WhenAuditJsonlLineMissesRequiredField()
    {
        var line = "{\"ts\":\"2026-03-10T12:00:00Z\",\"action\":\"url.deny\",\"reason\":\"offline_mode\",\"target\":\"https://example.com\"}";

        var isValid = HasRequiredAuditFields(line);

        isValid.Should().BeFalse();
    }

    [Theory]
    [InlineData(10, 0, true)]
    [InlineData(10, 1, false)]
    [InlineData(0, 0, false)]
    public void ShouldEvaluateGatePass_WhenAuditValidationSummaryIsProvided(int totalLines, int invalidLines, bool expected)
    {
        var gatePassed = EvaluateGatePass(totalLines, invalidLines);

        gatePassed.Should().Be(expected);
    }

    private static bool HasRequiredAuditFields(string jsonLine)
    {
        try
        {
            using var document = JsonDocument.Parse(jsonLine);
            var root = document.RootElement;

            return HasNonEmptyString(root, "ts")
                   && HasNonEmptyString(root, "action")
                   && HasNonEmptyString(root, "reason")
                   && HasNonEmptyString(root, "target")
                   && HasNonEmptyString(root, "caller");
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static bool HasNonEmptyString(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value))
        {
            return false;
        }

        return value.ValueKind == JsonValueKind.String
               && !string.IsNullOrWhiteSpace(value.GetString());
    }

    private static bool EvaluateGatePass(int totalLines, int invalidLines)
    {
        if (totalLines <= 0)
        {
            return false;
        }

        if (invalidLines < 0)
        {
            return false;
        }

        return invalidLines == 0;
    }
}

