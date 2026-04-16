namespace Game.Core.Contracts.Save;

/// <summary>
/// Continue gate decision produced from autosave migration validation.
/// </summary>
public sealed record ContinueGateDecision(
    bool ContinueAvailable,
    bool EnterGameAllowed,
    string? ErrorMessage,
    bool StateAdvanced
);
