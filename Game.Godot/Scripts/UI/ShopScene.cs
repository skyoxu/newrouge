using System;
using System.Collections.Generic;
using Godot;

namespace Game.Godot.Scripts.UI;

public partial class ShopScene : Control
{
    private sealed class ShopOffer
    {
        public ShopOffer(string id, int price, bool taken)
        {
            Id = id;
            Price = price;
            Taken = taken;
        }

        public string Id { get; set; }
        public int Price { get; set; }
        public bool Taken { get; set; }
    }

    private ItemList _offerList = default!;
    private Label _titleLabel = default!;
    private Button _buyButton = default!;
    private Label _goldValueLabel = default!;
    private Label _ownedOutcomeLabel = default!;
    private Label _removedOutcomeLabel = default!;
    private Label _failureReasonLabel = default!;
    private Button _removeButton = default!;
    private Button _reforgeButton = default!;
    private Button _leaveButton = default!;

    private readonly List<ShopOffer> _offers = new();
    private readonly HashSet<string> _ownedOfferIds = new(StringComparer.Ordinal);
    private readonly List<string> _removableCards = new();
    private readonly HashSet<string> _reforgeTargets = new(StringComparer.Ordinal);
    private readonly List<string> _failureReasons = new();
    private readonly List<string> _visibleOfferIds = new();
    private static readonly Dictionary<string, Dictionary<string, string>> TextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);
    private Node? _mainController;
    private string _lastRemovedCardId = string.Empty;
    private string _lastReforgedOfferId = string.Empty;
    private int _selectedVisibleOfferIndex = -1;
    private bool _leftShop;
    private int _playerGold;

    public override void _Ready()
    {
        _offerList = GetNode<ItemList>("VBox/OfferList");
        _titleLabel = GetNode<Label>("VBox/TitleLabel");
        _buyButton = GetNode<Button>("VBox/ServicesRow/BuyButton");
        _goldValueLabel = GetNode<Label>("VBox/GoldValueLabel");
        _ownedOutcomeLabel = GetNode<Label>("VBox/OwnedOutcomeLabel");
        _removedOutcomeLabel = GetNode<Label>("VBox/RemovedOutcomeLabel");
        _failureReasonLabel = GetNode<Label>("VBox/FailureReasonLabel");
        _removeButton = GetNode<Button>("VBox/ServicesRow/RemoveButton");
        _reforgeButton = GetNode<Button>("VBox/ServicesRow/ReforgeButton");
        _leaveButton = GetNode<Button>("VBox/LeaveButton");

        _offerList.ItemSelected += OnOfferSelected;
        _offerList.ItemActivated += OnOfferActivated;
        _buyButton.Pressed += OnBuyPressed;
        _removeButton.Pressed += OnRemovePressed;
        _reforgeButton.Pressed += OnReforgePressed;
        _leaveButton.Pressed += OnLeavePressed;
        _mainController = ResolveMainController();
        LocalizeVisibleText();
        TryLoadRouteOwnedState();
        RefreshUi();
    }

    public override void _ExitTree()
    {
        if (_offerList is not null)
        {
            _offerList.ItemSelected -= OnOfferSelected;
            _offerList.ItemActivated -= OnOfferActivated;
        }

        if (_buyButton is not null)
        {
            _buyButton.Pressed -= OnBuyPressed;
        }

        if (_removeButton is not null)
        {
            _removeButton.Pressed -= OnRemovePressed;
        }

        if (_reforgeButton is not null)
        {
            _reforgeButton.Pressed -= OnReforgePressed;
        }

        if (_leaveButton is not null)
        {
            _leaveButton.Pressed -= OnLeavePressed;
        }
    }

    public void SetShopStateForTest(global::Godot.Collections.Dictionary state)
    {
        _offers.Clear();
        _ownedOfferIds.Clear();
        _removableCards.Clear();
        _reforgeTargets.Clear();
        _failureReasons.Clear();
        _lastRemovedCardId = string.Empty;
        _lastReforgedOfferId = string.Empty;
        _selectedVisibleOfferIndex = -1;
        _leftShop = false;

        _playerGold = ReadInt(state, "gold", 0);

        var offers = ReadArray(state, "offers");
        foreach (var item in offers)
        {
            if (item.VariantType != Variant.Type.Dictionary)
            {
                continue;
            }

            var offer = item.AsGodotDictionary();
            var id = ReadString(offer, "id");
            if (string.IsNullOrWhiteSpace(id))
            {
                continue;
            }

            var price = ReadInt(offer, "price", 0);
            var taken = ReadBool(offer, "taken", false);
            _offers.Add(new ShopOffer(id, Math.Max(0, price), taken));
        }

        var owned = ReadArray(state, "owned_offer_ids");
        foreach (var id in owned)
        {
            var value = id.AsString();
            if (!string.IsNullOrWhiteSpace(value))
            {
                _ownedOfferIds.Add(value);
            }
        }

        var removable = ReadArray(state, "removable_cards");
        foreach (var cardId in removable)
        {
            var value = cardId.AsString();
            if (!string.IsNullOrWhiteSpace(value))
            {
                _removableCards.Add(value);
            }
        }

        var reforgeTargets = ReadArray(state, "reforge_targets");
        foreach (var offerId in reforgeTargets)
        {
            var value = offerId.AsString();
            if (!string.IsNullOrWhiteSpace(value))
            {
                _reforgeTargets.Add(value);
            }
        }

        var removedOutcome = ReadString(state, "removed_outcome");
        if (!string.IsNullOrWhiteSpace(removedOutcome))
        {
            _lastRemovedCardId = removedOutcome;
        }

        PersistRouteOwnedState();
        RefreshUi();
    }

    public global::Godot.Collections.Array<global::Godot.Collections.Dictionary> GetVisibleOffersForTest()
    {
        var result = new global::Godot.Collections.Array<global::Godot.Collections.Dictionary>();
        foreach (var offer in _offers)
        {
            if (offer.Taken)
            {
                continue;
            }

            result.Add(new global::Godot.Collections.Dictionary
            {
                { "id", offer.Id },
                { "price", offer.Price },
                { "taken", offer.Taken },
            });
        }

        return result;
    }

    public global::Godot.Collections.Array<string> GetOwnedOfferIdsForTest()
    {
        var owned = new global::Godot.Collections.Array<string>();
        foreach (var offerId in _ownedOfferIds)
        {
            owned.Add(offerId);
        }

        return owned;
    }

    public int GetPlayerGoldForTest()
    {
        return _playerGold;
    }

    public string GetLastRemovedCardIdForTest()
    {
        return _lastRemovedCardId;
    }

    public string GetLastReforgedOfferIdForTest()
    {
        return _lastReforgedOfferId;
    }

    public string GetLastRemovedOutcomeTextForTest()
    {
        return string.IsNullOrWhiteSpace(_lastRemovedCardId)
            ? string.Empty
            : FormatText(ResolveUiText("shop.feedback.remove_result"), _lastRemovedCardId);
    }

    public string GetLastReforgedOutcomeTextForTest()
    {
        return string.IsNullOrWhiteSpace(_lastReforgedOfferId)
            ? string.Empty
            : FormatText(ResolveUiText("shop.feedback.reforge_result"), _lastReforgedOfferId);
    }

    public string GetVisibleFailureReasonForTest()
    {
        return _failureReasonLabel.Text ?? string.Empty;
    }

    public void RefreshLocaleForTest()
    {
        LocalizeVisibleText();
    }

    public global::Godot.Collections.Dictionary PurchaseOfferForTest(string offerId)
    {
        if (string.IsNullOrWhiteSpace(offerId))
        {
            return Fail("invalid-offer", "invalid offer");
        }

        var offer = _offers.Find(candidate => string.Equals(candidate.Id, offerId, StringComparison.Ordinal));
        if (offer is null)
        {
            return Fail("invalid-offer", "invalid offer");
        }

        if (offer.Taken || _ownedOfferIds.Contains(offerId))
        {
            return Fail("offer-already-taken", "offer taken");
        }

        if (_playerGold < offer.Price)
        {
            return Fail("insufficient-resources", "insufficient resources");
        }

        _playerGold -= offer.Price;
        offer.Taken = true;
        _ownedOfferIds.Add(offerId);
        _failureReasonLabel.Text = string.Empty;
        PersistRouteOwnedState();
        RefreshUi();
        return Success();
    }

    public global::Godot.Collections.Dictionary RemoveCurseForTest(string cardId)
    {
        if (string.IsNullOrWhiteSpace(cardId))
        {
            return Fail("invalid-card", "invalid card");
        }

        if (!_removableCards.Remove(cardId))
        {
            return Fail("card-not-removable", "card not removable");
        }

        _lastRemovedCardId = cardId;
        _failureReasonLabel.Text = string.Empty;
        PersistRouteOwnedState();
        RefreshUi();
        return Success();
    }

    public global::Godot.Collections.Dictionary ReforgeOfferForTest(string offerId)
    {
        if (string.IsNullOrWhiteSpace(offerId))
        {
            return Fail("invalid-offer", "invalid offer");
        }

        if (!_reforgeTargets.Contains(offerId))
        {
            return Fail("offer-not-reforge-target", "offer not reforge target");
        }

        _lastReforgedOfferId = offerId;
        _failureReasonLabel.Text = string.Empty;
        PersistRouteOwnedState();
        RefreshUi();
        return Success();
    }

    public global::Godot.Collections.Dictionary LeaveShopForTest()
    {
        if (_leftShop)
        {
            return Fail("already-left", "already left");
        }

        var main = _mainController ?? ResolveMainController();
        if (main is null || !main.HasMethod("CompleteMapNodeFlowForTest"))
        {
            return Fail("route-controller-missing", "route controller missing");
        }

        var resultVariant = main.Call("CompleteMapNodeFlowForTest");
        if (resultVariant.VariantType != Variant.Type.Dictionary)
        {
            return Fail("route-result-invalid", "route result invalid");
        }

        var result = resultVariant.AsGodotDictionary();
        var ok = ReadBool(result, "ok", false);
        if (!ok)
        {
            var reason = ReadString(result, "reason");
            return Fail(string.IsNullOrWhiteSpace(reason) ? "route-failed" : reason, "route failed");
        }

        _leftShop = true;
        _failureReasonLabel.Text = ResolveUiText("shop.feedback.leave_route");
        return Success();
    }

    public void ShowLeaveRouteFeedbackForTest()
    {
        _failureReasonLabel.Text = ResolveUiText("shop.feedback.leave_route");
    }

    private void OnRemovePressed()
    {
        if (_removableCards.Count <= 0)
        {
            return;
        }

        RemoveCurseForTest(_removableCards[0]);
    }

    private void OnBuyPressed()
    {
        if (_selectedVisibleOfferIndex < 0 || _selectedVisibleOfferIndex >= _visibleOfferIds.Count)
        {
            Fail("offer-not-selected", "offer not selected");
            return;
        }

        _ = PurchaseOfferForTest(_visibleOfferIds[_selectedVisibleOfferIndex]);
    }

    private void OnOfferSelected(long index)
    {
        if (index < 0 || index >= _visibleOfferIds.Count)
        {
            _selectedVisibleOfferIndex = -1;
            _buyButton.Disabled = true;
            return;
        }

        _selectedVisibleOfferIndex = (int)index;
        _buyButton.Disabled = false;
    }

    private void OnOfferActivated(long index)
    {
        OnOfferSelected(index);
        OnBuyPressed();
    }

    private void OnReforgePressed()
    {
        foreach (var offerId in _reforgeTargets)
        {
            ReforgeOfferForTest(offerId);
            return;
        }
    }

    private void OnLeavePressed()
    {
        LeaveShopForTest();
    }

    private void RefreshUi()
    {
        _offerList.Clear();
        _visibleOfferIds.Clear();
        foreach (var offer in _offers)
        {
            if (offer.Taken)
            {
                continue;
            }

            _visibleOfferIds.Add(offer.Id);
            _offerList.AddItem($"{offer.Id} | price:{offer.Price}");
        }

        if (_visibleOfferIds.Count <= 0)
        {
            _selectedVisibleOfferIndex = -1;
            _buyButton.Disabled = true;
        }
        else
        {
            if (_selectedVisibleOfferIndex < 0 || _selectedVisibleOfferIndex >= _visibleOfferIds.Count)
            {
                _selectedVisibleOfferIndex = 0;
            }

            _offerList.Select(_selectedVisibleOfferIndex);
            _buyButton.Disabled = false;
        }

        _goldValueLabel.Text = _playerGold.ToString();
        _ownedOutcomeLabel.Text = _ownedOfferIds.Count > 0
            ? FormatText(ResolveUiText("shop.feedback.purchase_result"), string.Join(", ", _ownedOfferIds))
            : ResolveUiText("shop.feedback.no_purchase");
        _removedOutcomeLabel.Text = string.IsNullOrWhiteSpace(_lastRemovedCardId)
            ? ResolveUiText("shop.feedback.no_removal")
            : GetLastRemovedOutcomeTextForTest();
    }

    private void LocalizeVisibleText()
    {
        _titleLabel.Text = ResolveUiText("shop.title");
        _buyButton.Text = ResolveUiText("shop.service.buy");
        _removeButton.Text = ResolveUiText("shop.service.remove");
        _reforgeButton.Text = ResolveUiText("shop.service.reforge");
        _leaveButton.Text = ResolveUiText("shop.leave");
    }

    private static string ResolveUiText(string localizationKey)
    {
        if (string.IsNullOrWhiteSpace(localizationKey))
        {
            return string.Empty;
        }

        var locale = NormalizeLocale(TranslationServer.GetLocale());
        var map = GetTextMap(locale);
        if (map.TryGetValue(localizationKey, out var value) && !string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        if (!string.Equals(locale, "en", StringComparison.OrdinalIgnoreCase))
        {
            var fallback = GetTextMap("en");
            if (fallback.TryGetValue(localizationKey, out var fallbackValue) && !string.IsNullOrWhiteSpace(fallbackValue))
            {
                return fallbackValue;
            }
        }

        var localized = TranslationServer.Translate(localizationKey);
        return !string.Equals(localized, localizationKey, StringComparison.Ordinal) && IsReadableVisibleText(localized)
            ? localized
            : localizationKey;
    }

    private static bool IsReadableVisibleText(string value)
    {
        return !string.IsNullOrWhiteSpace(value)
            && !value.Contains("??", StringComparison.Ordinal)
            && !value.Contains('\uFFFD');
    }

    private static string NormalizeLocale(string locale)
    {
        if (string.IsNullOrWhiteSpace(locale))
        {
            return "en";
        }

        return locale.Trim().Replace('_', '-').ToLowerInvariant();
    }

    private static Dictionary<string, string> GetTextMap(string locale)
    {
        if (TextMapsByLocale.TryGetValue(locale, out var cached))
        {
            return cached;
        }

        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        var candidatePaths = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? new[] { "res://Game.Godot/Translations/zh-CN.csv", "res://../Game.Godot/Translations/zh-CN.csv" }
            : new[] { "res://Game.Godot/Translations/en.csv", "res://../Game.Godot/Translations/en.csv" };

        string raw = string.Empty;
        foreach (var candidatePath in candidatePaths)
        {
            if (!FileAccess.FileExists(candidatePath))
            {
                continue;
            }

            using var file = FileAccess.Open(candidatePath, FileAccess.ModeFlags.Read);
            if (file is null)
            {
                continue;
            }

            raw = file.GetAsText();
            break;
        }

        if (string.IsNullOrWhiteSpace(raw))
        {
            TextMapsByLocale[locale] = map;
            return map;
        }
        foreach (var line in raw.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrWhiteSpace(trimmed) || trimmed.StartsWith("key,value", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var separator = trimmed.IndexOf(',');
            if (separator <= 0 || separator >= trimmed.Length - 1)
            {
                continue;
            }

            var key = trimmed[..separator].Trim();
            var value = trimmed[(separator + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(key) && !string.IsNullOrWhiteSpace(value))
            {
                map[key] = value;
            }
        }

        TextMapsByLocale[locale] = map;
        return map;
    }

    private Node? ResolveMainController()
    {
        Node? current = this;
        while (current is not null)
        {
            if (current.HasMethod("CompleteMapNodeFlowForTest"))
            {
                return current;
            }

            current = current.GetParent();
        }

        return GetNodeOrNull<Node>("/root/Main");
    }

    private void TryLoadRouteOwnedState()
    {
        var main = _mainController;
        if (main is null || !main.HasMethod("GetActiveShopStateForScene"))
        {
            return;
        }

        var stateVariant = main.Call("GetActiveShopStateForScene");
        if (stateVariant.VariantType != Variant.Type.Dictionary)
        {
            return;
        }

        var state = stateVariant.AsGodotDictionary();
        if (state.Count <= 0)
        {
            return;
        }

        SetShopStateForTest(state);
    }

    private void PersistRouteOwnedState()
    {
        var main = _mainController;
        if (main is null || !main.HasMethod("ApplyShopStateForScene"))
        {
            return;
        }

        _ = main.Call("ApplyShopStateForScene", BuildCurrentStateSnapshot());
    }

    private global::Godot.Collections.Dictionary BuildCurrentStateSnapshot()
    {
        var offers = new global::Godot.Collections.Array<global::Godot.Collections.Dictionary>();
        foreach (var offer in _offers)
        {
            offers.Add(new global::Godot.Collections.Dictionary
            {
                { "id", offer.Id },
                { "price", offer.Price },
                { "taken", offer.Taken },
            });
        }

        var owned = new global::Godot.Collections.Array<string>();
        foreach (var offerId in _ownedOfferIds)
        {
            owned.Add(offerId);
        }

        var removable = new global::Godot.Collections.Array<string>();
        foreach (var cardId in _removableCards)
        {
            removable.Add(cardId);
        }

        var reforgeTargets = new global::Godot.Collections.Array<string>();
        foreach (var offerId in _reforgeTargets)
        {
            reforgeTargets.Add(offerId);
        }

        return new global::Godot.Collections.Dictionary
        {
            { "gold", _playerGold },
            { "offers", offers },
            { "owned_offer_ids", owned },
            { "removable_cards", removable },
            { "reforge_targets", reforgeTargets },
            { "removed_outcome", _lastRemovedCardId },
        };
    }

    private global::Godot.Collections.Dictionary Success()
    {
        return new global::Godot.Collections.Dictionary
        {
            { "ok", true },
            { "reason", string.Empty },
        };
    }

    private global::Godot.Collections.Dictionary Fail(string reasonCode, string reasonText)
    {
        var visibleReason = ResolveFailureReason(reasonCode, reasonText);
        _failureReasons.Add(visibleReason);
        _failureReasonLabel.Text = string.Join("; ", _failureReasons);

        return new global::Godot.Collections.Dictionary
        {
            { "ok", false },
            { "reason", reasonCode },
        };
    }

    private static string ResolveFailureReason(string reasonCode, string fallback)
    {
        var key = reasonCode switch
        {
            "insufficient-resources" => "shop.feedback.insufficient_gold",
            "offer-already-taken" => "shop.feedback.offer_taken",
            "invalid-offer" => "shop.feedback.invalid_offer",
            "offer-not-selected" => "shop.feedback.invalid_offer",
            "invalid-card" => "shop.feedback.invalid_card",
            "card-not-removable" => "shop.feedback.card_not_removable",
            "offer-not-reforge-target" => "shop.feedback.not_reforge_target",
            "already-left" => "shop.feedback.already_left",
            "route-controller-missing" => "shop.feedback.route_missing",
            "route-result-invalid" => "shop.feedback.route_failed",
            "route-failed" => "shop.feedback.route_failed",
            _ => string.Empty,
        };

        var resolved = string.IsNullOrWhiteSpace(key) ? string.Empty : ResolveUiText(key);
        return string.IsNullOrWhiteSpace(resolved) || string.Equals(resolved, key, StringComparison.Ordinal)
            ? fallback
            : resolved;
    }

    private static string FormatText(string template, string value)
    {
        return string.IsNullOrWhiteSpace(template)
            ? value
            : template.Replace("{0}", value, StringComparison.Ordinal);
    }

    private static global::Godot.Collections.Array ReadArray(global::Godot.Collections.Dictionary source, string key)
    {
        if (source.TryGetValue(key, out var value) && value.VariantType == Variant.Type.Array)
        {
            return value.AsGodotArray();
        }

        return new global::Godot.Collections.Array();
    }

    private static string ReadString(global::Godot.Collections.Dictionary source, string key)
    {
        if (source.TryGetValue(key, out var value))
        {
            return value.AsString();
        }

        return string.Empty;
    }

    private static int ReadInt(global::Godot.Collections.Dictionary source, string key, int fallback)
    {
        if (!source.TryGetValue(key, out var value))
        {
            return fallback;
        }

        return value.VariantType switch
        {
            Variant.Type.Int => (int)value,
            Variant.Type.Float => (int)(double)value,
            Variant.Type.String when int.TryParse(value.AsString(), out var parsed) => parsed,
            _ => fallback,
        };
    }

    private static bool ReadBool(global::Godot.Collections.Dictionary source, string key, bool fallback)
    {
        if (!source.TryGetValue(key, out var value))
        {
            return fallback;
        }

        return value.VariantType switch
        {
            Variant.Type.Bool => (bool)value,
            Variant.Type.Int => (int)value != 0,
            Variant.Type.String when bool.TryParse(value.AsString(), out var parsed) => parsed,
            _ => fallback,
        };
    }
}
