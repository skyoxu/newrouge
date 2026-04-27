using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Game.Core.Services;
using Godot;

namespace Game.Godot.Scripts.Reward;

/// <summary>
/// Bridges Reward first-entry offer generation into the shared CardPool path.
/// </summary>
public partial class RewardOfferProvider : Node
{
    private sealed record CardTextMetadata(string NameKey, string DescriptionKey, string Form);

    private static readonly Lazy<IReadOnlyDictionary<string, CardTextMetadata>> CardTextCatalog =
        new(LoadCardTextCatalog);

    private readonly OfferPreviewService _offerPreviewService = new();

    public global::Godot.Collections.Array<global::Godot.Collections.Dictionary> BuildFirstEntryOfferForContext(
        int actId,
        string encounterType,
        int deterministicSeed,
        long streamPosition = 0,
        int pickCount = 3)
    {
        var offers = new global::Godot.Collections.Array<global::Godot.Collections.Dictionary>();
        if (pickCount <= 0)
        {
            return offers;
        }

        try
        {
            var preview = _offerPreviewService.PreviewSelection(
                act: actId,
                encounterType: encounterType,
                seed: deterministicSeed,
                streamPosition: streamPosition,
                pickCount: pickCount);

            var index = 0;
            foreach (var cardId in preview.SelectedCardIds)
            {
                index += 1;
                var metadata = ResolveCardTextMetadata(cardId);
                offers.Add(new global::Godot.Collections.Dictionary
                {
                    { "id", cardId },
                    { "name_key", metadata.NameKey },
                    { "description_key", metadata.DescriptionKey },
                    { "name", metadata.NameKey },
                    { "description", metadata.DescriptionKey },
                    { "form", metadata.Form },
                    { "selectable", true },
                    { "source", "shared-card-pool" },
                    { "offer_index", index },
                });
            }
        }
        catch (Exception ex)
        {
            GD.PushWarning($"[RewardOfferProvider] failed to build first-entry offer: {ex.Message}");
        }

        return offers;
    }

    private static CardTextMetadata ResolveCardTextMetadata(string cardId)
    {
        if (!string.IsNullOrWhiteSpace(cardId) && CardTextCatalog.Value.TryGetValue(cardId, out var metadata))
        {
            return metadata;
        }

        var normalized = string.IsNullOrWhiteSpace(cardId) ? "card.unknown" : cardId.Trim();
        return new CardTextMetadata(
            NameKey: normalized + ".name",
            DescriptionKey: normalized + ".description",
            Form: "Base");
    }

    private static IReadOnlyDictionary<string, CardTextMetadata> LoadCardTextCatalog()
    {
        var map = new Dictionary<string, CardTextMetadata>(StringComparer.Ordinal);
        var path = ProjectSettings.GlobalizePath("res://../Game.Core/Data/m1-card-definitions.json");
        if (!File.Exists(path))
        {
            GD.PushWarning($"[RewardOfferProvider] card definition file not found: {path}");
            return map;
        }

        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            if (!doc.RootElement.TryGetProperty("cards", out var cards) || cards.ValueKind != JsonValueKind.Array)
            {
                return map;
            }

            foreach (var card in cards.EnumerateArray())
            {
                if (!TryReadString(card, "id", out var id) ||
                    !TryReadString(card, "name_key", out var nameKey) ||
                    !TryReadString(card, "description_key", out var descriptionKey))
                {
                    continue;
                }

                var form = "Base";
                if (TryReadString(card, "default_form", out var defaultForm) && !string.IsNullOrWhiteSpace(defaultForm))
                {
                    form = defaultForm.Trim();
                }

                map[id] = new CardTextMetadata(
                    NameKey: nameKey,
                    DescriptionKey: descriptionKey,
                    Form: form);
            }
        }
        catch (Exception ex)
        {
            GD.PushWarning($"[RewardOfferProvider] failed to load card definition metadata: {ex.Message}");
        }

        return map;
    }

    private static bool TryReadString(JsonElement source, string key, out string value)
    {
        value = string.Empty;
        if (!source.TryGetProperty(key, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var text = property.GetString();
        if (string.IsNullOrWhiteSpace(text))
        {
            return false;
        }

        value = text.Trim();
        return true;
    }
}
