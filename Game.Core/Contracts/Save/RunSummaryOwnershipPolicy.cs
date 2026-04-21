using System;

namespace Game.Core.Contracts.Save;

/// <summary>
/// Policy: exactly one run summary owner must be selected.
/// </summary>
public sealed class RunSummaryOwnershipPolicy
{
    public RunSummaryOwnershipValidationResult Validate(RunSummaryOwnershipSelection selection)
    {
        ArgumentNullException.ThrowIfNull(selection);
        var owners = selection.SelectedOwners;
        return new RunSummaryOwnershipValidationResult(owners.Length == 1);
    }
}
