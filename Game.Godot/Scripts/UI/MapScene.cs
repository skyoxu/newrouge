using System;
using System.Collections.Generic;
using System.IO;
using Godot;

namespace Game.Godot.Scripts.UI;

public partial class MapScene : Control
{
    private const string TitleKey = "ui.map.title";
    private const string HintKey = "ui.map.hint";
    private const string CombatActionKey = "ui.map.action.combat";
    private const string EventActionKey = "ui.map.action.event";
    private const string ShopActionKey = "ui.map.action.shop";
    private const string RestActionKey = "ui.map.action.rest";

    private static readonly Dictionary<string, Dictionary<string, string>> TextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);

    private Label _titleLabel = default!;
    private Label _hintLabel = default!;
    private Button _combatButton = default!;
    private Button _eventButton = default!;
    private Button _shopButton = default!;
    private Button _restButton = default!;
    private string _lastLocale = string.Empty;
    private string _lastInvokedAction = string.Empty;

    public override void _Ready()
    {
        _titleLabel = GetNode<Label>("title_label");
        _hintLabel = GetNode<Label>("hint_label");
        _combatButton = GetNode<Button>("ActionRow/btn_combat");
        _eventButton = GetNode<Button>("ActionRow/btn_event");
        _shopButton = GetNode<Button>("ActionRow/btn_shop");
        _restButton = GetNode<Button>("ActionRow/btn_rest");
        _combatButton.Pressed += OnCombatPressed;
        _eventButton.Pressed += OnEventPressed;
        _shopButton.Pressed += OnShopPressed;
        _restButton.Pressed += OnRestPressed;
        RefreshVisibleTextForTest();
    }

    public override void _ExitTree()
    {
        if (_combatButton is not null)
        {
            _combatButton.Pressed -= OnCombatPressed;
        }

        if (_eventButton is not null)
        {
            _eventButton.Pressed -= OnEventPressed;
        }

        if (_shopButton is not null)
        {
            _shopButton.Pressed -= OnShopPressed;
        }

        if (_restButton is not null)
        {
            _restButton.Pressed -= OnRestPressed;
        }
    }

    public override void _Process(double _delta)
    {
        var locale = NormalizeLocale(TranslationServer.GetLocale());
        if (string.Equals(locale, _lastLocale, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        ApplyLocalizedText(locale);
    }

    public void RefreshVisibleTextForTest()
    {
        ApplyLocalizedText(NormalizeLocale(TranslationServer.GetLocale()));
    }

    public void RefreshLocaleForTest()
    {
        RefreshVisibleTextForTest();
    }

    public bool InvokeActionForTest(string action)
    {
        if (string.IsNullOrWhiteSpace(action))
        {
            return false;
        }

        var normalized = action.Trim().ToLowerInvariant();
        switch (normalized)
        {
            case "combat":
                _combatButton.EmitSignal(BaseButton.SignalName.Pressed);
                return true;
            case "event":
                _eventButton.EmitSignal(BaseButton.SignalName.Pressed);
                return true;
            case "shop":
                _shopButton.EmitSignal(BaseButton.SignalName.Pressed);
                return true;
            case "rest":
                _restButton.EmitSignal(BaseButton.SignalName.Pressed);
                return true;
            default:
                return false;
        }
    }

    public string GetLastInvokedActionForTest()
    {
        return _lastInvokedAction;
    }

    private void ApplyLocalizedText(string locale)
    {
        _lastLocale = locale;
        _titleLabel.Text = ResolveVisibleText(TitleKey, locale);
        _hintLabel.Text = ResolveVisibleText(HintKey, locale);
        _combatButton.Text = ResolveVisibleTextOrFallback(CombatActionKey, locale, "Combat");
        _eventButton.Text = ResolveVisibleTextOrFallback(EventActionKey, locale, "Event");
        _shopButton.Text = ResolveVisibleTextOrFallback(ShopActionKey, locale, "Shop");
        _restButton.Text = ResolveVisibleTextOrFallback(RestActionKey, locale, "Rest");
    }

    private static string ResolveVisibleTextOrFallback(string key, string locale, string fallback)
    {
        var resolved = ResolveVisibleText(key, locale);
        if (string.Equals(resolved, key, StringComparison.Ordinal))
        {
            return fallback;
        }

        return resolved;
    }

    private void OnCombatPressed()
    {
        _lastInvokedAction = "combat";
    }

    private void OnEventPressed()
    {
        _lastInvokedAction = "event";
    }

    private void OnShopPressed()
    {
        _lastInvokedAction = "shop";
    }

    private void OnRestPressed()
    {
        _lastInvokedAction = "rest";
    }

    private static string ResolveVisibleText(string key, string locale)
    {
        var localized = TranslationServer.Translate(key);
        if (!string.Equals(localized, key, StringComparison.Ordinal))
        {
            return localized;
        }

        var map = GetTextMap(locale);
        if (map.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        if (!string.Equals(locale, "en", StringComparison.OrdinalIgnoreCase))
        {
            var fallback = GetTextMap("en");
            if (fallback.TryGetValue(key, out var fallbackValue) && !string.IsNullOrWhiteSpace(fallbackValue))
            {
                return fallbackValue;
            }
        }

        return key;
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

        string? raw = null;
        foreach (var candidate in candidatePaths)
        {
            var absolutePath = ProjectSettings.GlobalizePath(candidate);
            if (!File.Exists(absolutePath))
            {
                continue;
            }

            raw = File.ReadAllText(absolutePath);
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

            var mapKey = trimmed[..separator].Trim();
            var mapValue = trimmed[(separator + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(mapKey) && !string.IsNullOrWhiteSpace(mapValue))
            {
                map[mapKey] = mapValue;
            }
        }

        TextMapsByLocale[locale] = map;
        return map;
    }

    private static string NormalizeLocale(string locale)
    {
        if (string.IsNullOrWhiteSpace(locale))
        {
            return "en";
        }

        return locale.Trim().Replace('_', '-').ToLowerInvariant();
    }
}
