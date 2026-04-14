using Game.Core.Contracts.Status;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Status apply/stack/expire operations.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0007, ADR-0033, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface IStatusService
{
    StatusInstance Apply(StatusInstance current, StatusInstance incoming);
    void ApplyToTarget(IDictionary<string, StatusInstance> targetStatuses, StatusInstance incoming);
    StatusInstance Tick(StatusInstance current, ExpiresTiming timing);
    void ProcessTurnPhase(IDictionary<string, StatusInstance> targetStatuses, ExpiresTiming timing);
    IReadOnlyList<StatusInstance> Dispel(IEnumerable<StatusInstance> statuses);
    void DispelDebuffs(IDictionary<string, StatusInstance> targetStatuses);
    bool TryApplyRage(IDictionary<string, StatusInstance> targetStatuses, int stacks, string sourceId);
    int GetRageStacks(IReadOnlyDictionary<string, StatusInstance> targetStatuses);
    void ResetCombatOnlyStatuses(IDictionary<string, StatusInstance> targetStatuses);
}
