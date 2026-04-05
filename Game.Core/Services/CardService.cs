using Game.Core.Contracts.Cards;

namespace Game.Core.Services;

/// <summary>
/// Domain-level helper for deterministic card identity, upgrade path and lookup behavior.
/// </summary>
public sealed class CardService
{
    private const string NotFoundErrorCode = "card.definition.not_found";
    private const string NotFoundErrorType = "card_definition_not_found";

    public (CardDefinition? definition, string? errorCode, string? errorType) GetCardDefinition(
        IReadOnlyCollection<CardDefinition> definitions,
        string cardId)
    {
        foreach (var definition in definitions)
        {
            if (string.Equals(definition.CardId, cardId, StringComparison.Ordinal))
            {
                return (definition, null, null);
            }
        }

        return (null, NotFoundErrorCode, NotFoundErrorType);
    }

    public CardInstance CreateCardInstance(
        CardDefinition definition,
        string instanceId,
        IReadOnlyList<CardInstanceModifier>? permanentModifiers = null)
    {
        return new CardInstance(
            instanceId: instanceId,
            cardId: definition.CardId,
            form: CardForm.Base,
            route: null,
            upgradeTier: 0,
            permanentCardInstanceModifiers: permanentModifiers ?? Array.Empty<CardInstanceModifier>());
    }

    public CardInstance UpgradeToU1(CardInstance sourceInstance, UpgradeRoute route)
    {
        if (!Enum.IsDefined(typeof(UpgradeRoute), route))
        {
            throw new ArgumentException("route must be A or B.", nameof(route));
        }

        if (sourceInstance.IsUltimate)
        {
            throw new InvalidOperationException("ultimate form cannot be upgraded to U1.");
        }

        if (sourceInstance.Form != CardForm.Base || sourceInstance.UpgradeTier != 0 || sourceInstance.Route is not null)
        {
            throw new ArgumentException("source instance must be base form with tier 0 and null route.", nameof(sourceInstance));
        }

        var targetForm = route == UpgradeRoute.A ? CardForm.U1A : CardForm.U1B;
        return new CardInstance(
            instanceId: sourceInstance.InstanceId,
            cardId: sourceInstance.CardId,
            form: targetForm,
            route: route,
            upgradeTier: 1,
            permanentCardInstanceModifiers: sourceInstance.PermanentCardInstanceModifiers);
    }

    public CardInstance PromoteToUltimate(CardInstance sourceInstance)
    {
        if (sourceInstance.IsUltimate)
        {
            throw new InvalidOperationException("ultimate form is final and cannot be promoted again.");
        }

        var isU1Form = sourceInstance.Form is CardForm.U1A or CardForm.U1B;
        if (!isU1Form || sourceInstance.UpgradeTier != 1 || sourceInstance.Route is null)
        {
            throw new ArgumentException("only U1 instances with a valid route can be promoted to ultimate.", nameof(sourceInstance));
        }

        return new CardInstance(
            instanceId: sourceInstance.InstanceId,
            cardId: sourceInstance.CardId,
            form: CardForm.Ultimate,
            route: null,
            upgradeTier: 2,
            permanentCardInstanceModifiers: sourceInstance.PermanentCardInstanceModifiers);
    }

    public string ResolveEffectKey(CardInstance instance)
    {
        return instance.Form switch
        {
            CardForm.Base => "card.effect.base",
            CardForm.U1A => "card.effect.u1.route_a",
            CardForm.U1B => "card.effect.u1.route_b",
            CardForm.Ultimate => "card.effect.ultimate",
            _ => "card.effect.unknown",
        };
    }
}
