using Game.Core.Contracts.Config;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Act configuration provider.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0007, ADR-0033.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface IActConfigProvider
{
    ActConfig GetByActId(int actId);
}
