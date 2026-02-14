using Game.Core.Contracts.Content;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Curse add/remove service.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0007, ADR-0033.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface ICurseService
{
    CurseDefinition AddCurse(string cardId);
    bool RemoveCurse(string cardId);
}
