using Game.Core.Contracts.Config;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Act configuration provider abstraction.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0007, ADR-0006, ADR-0031.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface IActConfigProvider
{
    /// <summary>
    /// Resolve act configuration for a specific <c>act_id</c>.
    /// </summary>
    ActConfig GetByActId(int actId);
}
