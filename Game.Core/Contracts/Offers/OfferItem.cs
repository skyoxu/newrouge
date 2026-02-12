using Game.Core.Contracts.Cards;

namespace Game.Core.Contracts.Offers;

/// <summary>
/// One candidate item shown in an offer panel.
/// </summary>
public sealed record OfferItem(
    string OfferItemId,
    string CardId,
    CardForm Form,
    UpgradeRoute? Route,
    string Rarity
);

