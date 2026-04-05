namespace Game.Core.Contracts.Cards;

/// <summary>
/// Runtime instance of a card owned in a run.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0033, ADR-0020.
/// </remarks>
public sealed record CardInstance
{
    public CardInstance(
        string instanceId,
        string cardId,
        CardForm form,
        UpgradeRoute? route,
        int upgradeTier,
        IReadOnlyList<CardInstanceModifier> permanentCardInstanceModifiers
    )
    {
        if (upgradeTier is < 0 or > 2)
        {
            throw new ArgumentException("upgradeTier must be between 0 and 2.", nameof(upgradeTier));
        }

        if (upgradeTier == 1 && (form == CardForm.U1A || form == CardForm.U1B) && route is null)
        {
            throw new ArgumentException("when tier is 1 and form is U1A/U1B, route is required.", nameof(route));
        }

        if (upgradeTier == 2 && route is not null)
        {
            throw new ArgumentException("when tier is 2, route must be null.", nameof(route));
        }

        if (route is not null && !Enum.IsDefined(typeof(UpgradeRoute), route.Value))
        {
            throw new ArgumentException("route must be A or B when provided.", nameof(route));
        }

        this.InstanceId = string.IsNullOrWhiteSpace(instanceId)
            ? throw new ArgumentException("instanceId is required.", nameof(instanceId))
            : instanceId;
        this.CardId = string.IsNullOrWhiteSpace(cardId)
            ? throw new ArgumentException("cardId is required.", nameof(cardId))
            : cardId;
        this.Form = form;
        this.Route = route;
        this.UpgradeTier = upgradeTier;
        this.PermanentCardInstanceModifiers = permanentCardInstanceModifiers is null
            ? Array.Empty<CardInstanceModifier>()
            : permanentCardInstanceModifiers.ToArray();
    }

    public string InstanceId { get; }

    public string CardId { get; }

    public CardForm Form { get; }

    public UpgradeRoute? Route { get; }

    public int UpgradeTier { get; }

    public IReadOnlyList<CardInstanceModifier> PermanentCardInstanceModifiers { get; }

    public bool IsUltimate => Form == CardForm.Ultimate;
}
