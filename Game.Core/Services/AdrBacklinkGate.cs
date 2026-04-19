using System;
using System.Collections.Generic;
using System.Linq;
using Game.Core.Contracts.Save;

namespace Game.Core.Services;

/// <summary>
/// Evaluates required ADR backlink evidence for acceptance gating.
/// </summary>
public static class AdrBacklinkGate
{
    public static ContinueLoadValidationResult Evaluate(
        IEnumerable<string> requiredAdrIds,
        IReadOnlyDictionary<string, string> evidenceByAdrId)
    {
        ArgumentNullException.ThrowIfNull(requiredAdrIds);
        ArgumentNullException.ThrowIfNull(evidenceByAdrId);

        var missing = requiredAdrIds
            .Where(adrId =>
            {
                if (string.IsNullOrWhiteSpace(adrId))
                {
                    return false;
                }

                return !evidenceByAdrId.TryGetValue(adrId, out var path) || string.IsNullOrWhiteSpace(path);
            })
            .ToArray();

        if (missing.Length == 0)
        {
            return new ContinueLoadValidationResult(true, null, null);
        }

        return new ContinueLoadValidationResult(
            ContinueAllowed: false,
            ErrorCode: "missing_adr_backlink",
            ErrorMessage: $"Missing ADR evidence: {string.Join(", ", missing)}");
    }
}
