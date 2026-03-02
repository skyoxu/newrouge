namespace Game.Core.Contracts;

/// <summary>
/// Canonical RNG stream categories used by deterministic systems.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Feature-Slice-M1-Warrior.md
/// </remarks>
public static class RngStreamType
{
    public const string Run = "run";
    public const string Combat = "combat";
    public const string Event = "event";
    public const string Loot = "loot";
    public const string Shop = "shop";
    public const string Offer = "offer";
}
