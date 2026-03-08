namespace Game.Core.Contracts.Config;

/// <summary>
/// Result payload for ActConfig loading operations.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0006, ADR-0031, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record ActConfigLoadResult(
    bool IsSuccess,
    ActConfig? Config,
    string? ErrorCode,
    string? ErrorMessage,
    string Source
)
{
    /// <summary>
    /// Creates a successful load result.
    /// </summary>
    public static ActConfigLoadResult Success(ActConfig config, string source)
    {
        ArgumentNullException.ThrowIfNull(config);
        return new ActConfigLoadResult(true, config, null, null, source);
    }

    /// <summary>
    /// Creates a failed load result with explicit error details.
    /// </summary>
    public static ActConfigLoadResult Failure(string errorCode, string errorMessage, string source)
    {
        if (string.IsNullOrWhiteSpace(errorCode))
        {
            throw new ArgumentException("Error code must be non-empty.", nameof(errorCode));
        }

        if (string.IsNullOrWhiteSpace(errorMessage))
        {
            throw new ArgumentException("Error message must be non-empty.", nameof(errorMessage));
        }

        return new ActConfigLoadResult(false, null, errorCode, errorMessage, source);
    }
}
