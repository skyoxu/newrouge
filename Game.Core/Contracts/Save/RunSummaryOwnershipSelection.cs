using System;

namespace Game.Core.Contracts.Save;

/// <summary>
/// Immutable ownership declaration for run summary UI.
/// </summary>
public sealed class RunSummaryOwnershipSelection
{
    public RunSummaryOwnershipSelection(RunSummaryOwnerSurface[] selectedOwners)
    {
        ArgumentNullException.ThrowIfNull(selectedOwners);
        SelectedOwners = (RunSummaryOwnerSurface[])selectedOwners.Clone();
    }

    public RunSummaryOwnerSurface[] SelectedOwners { get; }
}
