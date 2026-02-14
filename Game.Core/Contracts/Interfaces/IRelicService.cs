using Game.Core.Contracts.Content;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Relic grant/query service.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0007, ADR-0033.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface IRelicService
{
    RelicInstance Grant(RelicDefinition definition, string source);
}
