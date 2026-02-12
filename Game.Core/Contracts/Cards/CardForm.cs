namespace Game.Core.Contracts.Cards;

/// <summary>
/// Card form for one logical card identity.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0033, ADR-0004.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public enum CardForm
{
    Base = 0,
    U1A = 1,
    U1B = 2,
    Ultimate = 3,
}

