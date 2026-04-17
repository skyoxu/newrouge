namespace Game.Core.Contracts.Save;

/// <summary>
/// Validation result for loading single-slot continue data.
/// </summary>
public sealed record ContinueLoadValidationResult(
    bool ContinueAllowed,
    string? ErrorCode,
    string? ErrorMessage
);
