namespace Game.Core.Contracts.Save;

/// <summary>
/// Validation result for run summary ownership policy.
/// </summary>
public sealed class RunSummaryOwnershipValidationResult
{
    public RunSummaryOwnershipValidationResult(bool isAccepted)
    {
        IsAccepted = isAccepted;
    }

    public bool IsAccepted { get; }
}
