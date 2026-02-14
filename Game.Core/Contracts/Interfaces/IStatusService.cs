using Game.Core.Contracts.Status;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Status apply/stack/expire operations.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0007, ADR-0033.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface IStatusService
{
    StatusInstance Apply(StatusInstance current, StatusInstance incoming);
    StatusInstance Tick(StatusInstance current, ExpiresTiming timing);
}
