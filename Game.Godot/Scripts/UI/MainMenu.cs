using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Godot;
using Game.Core.Contracts;
using Game.Core.Contracts.Save;
using Game.Godot.Adapters;

namespace Game.Godot.Scripts.UI;

public partial class MainMenu : Control
{
    private const string AutosavePath = "user://autosave_slot.json";
    private const int SupportedSchemaMajor = 1;

    private static readonly JsonDocumentOptions AutosaveJsonOptions = new()
    {
        MaxDepth = 16
    };

    private Button _btnNewRun = default!;
    private Button _btnContinue = default!;
    private Button _btnQuit = default!;
    private ConfirmationDialog? _overwriteConfirmDialog;
    private Control? _continueBlockedDialog;
    private Label? _continueBlockedTitleLabel;
    private Label? _continueBlockedMessageLabel;
    private Button? _continueBlockedNewRunButton;
    private Button? _continueBlockedCancelButton;
    private Button? _continueBlockedReturnButton;
    private bool? _autosaveAvailableOverride;
    private bool _disableQuitForTests;
    private bool _quitRequested;
    private bool _quitIntentReachedForTest;
    private bool _hasQuitRequestCallbackForTest;
    private Callable _quitRequestCallbackForTest;
    private string _lastDialogFocusPreferenceForTest = string.Empty;
    private static Dictionary<string, string>? _menuTextFallbacks;
    private string _lastLocaleForRuntimeRefresh = string.Empty;

    public override void _Ready()
    {
        _btnNewRun = GetNode<Button>("VBox/BtnNewRun");
        _btnContinue = GetNode<Button>("VBox/BtnContinue");
        _btnQuit = GetNode<Button>("VBox/BtnQuit");
        _overwriteConfirmDialog = GetNodeOrNull<ConfirmationDialog>("OverwriteConfirmDialog");
        _continueBlockedDialog = GetNodeOrNull<Control>("ContinueBlockedDialog");
        _continueBlockedTitleLabel = GetNodeOrNull<Label>("ContinueBlockedDialog/MarginContainer/VBox/TitleLabel");
        _continueBlockedMessageLabel = GetNodeOrNull<Label>("ContinueBlockedDialog/MarginContainer/VBox/MessageLabel");
        _continueBlockedNewRunButton = GetNodeOrNull<Button>("ContinueBlockedDialog/MarginContainer/VBox/ButtonRow/BtnNewRun");
        _continueBlockedCancelButton = GetNodeOrNull<Button>("ContinueBlockedDialog/MarginContainer/VBox/ButtonRow/BtnCancel");
        _continueBlockedReturnButton = GetNodeOrNull<Button>("ContinueBlockedDialog/MarginContainer/VBox/ButtonRow/BtnReturnToMenu");

        _menuTextFallbacks = null;
        DisableAutoTranslationForManagedMenuText();
        LocalizeVisibleText();
        HideContinueBlockedDialog(clearMessage: true);
        RefreshContinueAvailability();

        _btnNewRun.Pressed += OnNewRunPressed;
        _btnContinue.Pressed += OnContinuePressed;
        _btnQuit.Pressed += OnQuitPressed;
        if (_overwriteConfirmDialog is not null)
        {
            _overwriteConfirmDialog.Confirmed += OnOverwriteConfirmed;
            _overwriteConfirmDialog.Canceled += OnOverwriteCanceled;
        }
        if (_continueBlockedNewRunButton is not null)
        {
            _continueBlockedNewRunButton.Pressed += OnContinueBlockedNewRunPressed;
        }
        if (_continueBlockedCancelButton is not null)
        {
            _continueBlockedCancelButton.Pressed += OnContinueBlockedDismissed;
        }
        if (_continueBlockedReturnButton is not null)
        {
            _continueBlockedReturnButton.Pressed += OnContinueBlockedDismissed;
        }

        _lastLocaleForRuntimeRefresh = NormalizeLocale(TranslationServer.GetLocale());
    }

    private void DisableAutoTranslationForManagedMenuText()
    {
        _btnNewRun.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _btnContinue.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _btnQuit.AutoTranslateMode = AutoTranslateModeEnum.Disabled;

        if (_overwriteConfirmDialog is not null)
        {
            _overwriteConfirmDialog.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        }
        if (_continueBlockedTitleLabel is not null)
        {
            _continueBlockedTitleLabel.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        }
        if (_continueBlockedMessageLabel is not null)
        {
            _continueBlockedMessageLabel.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        }
        if (_continueBlockedNewRunButton is not null)
        {
            _continueBlockedNewRunButton.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        }
        if (_continueBlockedCancelButton is not null)
        {
            _continueBlockedCancelButton.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        }
        if (_continueBlockedReturnButton is not null)
        {
            _continueBlockedReturnButton.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        }
    }

    public override void _Process(double _delta)
    {
        var locale = NormalizeLocale(TranslationServer.GetLocale());
        if (string.Equals(locale, _lastLocaleForRuntimeRefresh, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        _lastLocaleForRuntimeRefresh = locale;
        _menuTextFallbacks = null;
        LocalizeVisibleText();
    }

    public void ShowMenu() => Visible = true;
    public void HideMenu() => Visible = false;
    public void SetAutosaveAvailableForTest(bool value)
    {
        _autosaveAvailableOverride = value;
        RefreshContinueAvailability();
    }

    public void SetDisableQuitForTests(bool value)
    {
        _disableQuitForTests = value;
    }

    public bool WasQuitRequestedForTest()
    {
        return _quitRequested;
    }

    public bool WasQuitIntentReachedForTest()
    {
        return _quitIntentReachedForTest;
    }

    public string GetLastDialogFocusPreferenceForTest()
    {
        return _lastDialogFocusPreferenceForTest;
    }

    public void SetQuitRequestCallbackForTest(Callable callback)
    {
        _quitRequestCallbackForTest = callback;
        _hasQuitRequestCallbackForTest = true;
    }

    public void RefreshVisibleTextForTest()
    {
        _menuTextFallbacks = null;
        LocalizeVisibleText();
    }

    public bool InvokePrimaryActionForTest(string actionId)
    {
        var normalized = actionId?.Trim().ToLowerInvariant() ?? string.Empty;
        switch (normalized)
        {
            case "new_run":
                OnNewRunPressed();
                return true;
            case "continue":
                OnContinuePressed();
                return true;
            case "quit":
                OnQuitPressed();
                return true;
            default:
                return false;
        }
    }

    private void LocalizeVisibleText()
    {
        _btnNewRun.Text = ResolveVisibleText("ui.menu.new_run");
        _btnContinue.Text = ResolveVisibleText("ui.menu.continue");
        _btnQuit.Text = ResolveVisibleText("ui.menu.quit");

        if (_overwriteConfirmDialog is null)
        {
            LocalizeContinueBlockedDialogText();
            return;
        }

        _overwriteConfirmDialog.Title = ResolveVisibleText("ui.menu.confirm_overwrite.title");
        _overwriteConfirmDialog.DialogText = ResolveVisibleText("ui.menu.confirm_overwrite.body");
        _overwriteConfirmDialog.OkButtonText = ResolveVisibleText("ui.menu.confirm");
        _overwriteConfirmDialog.CancelButtonText = ResolveVisibleText("ui.menu.cancel");
        LocalizeContinueBlockedDialogText();
    }

    private void LocalizeContinueBlockedDialogText()
    {
        if (_continueBlockedTitleLabel is not null)
        {
            _continueBlockedTitleLabel.Text = ResolveVisibleText("ui.menu.continue_blocked.title");
        }
        if (_continueBlockedNewRunButton is not null)
        {
            _continueBlockedNewRunButton.Text = ResolveVisibleText("ui.menu.continue_blocked.new_run");
        }
        if (_continueBlockedCancelButton is not null)
        {
            _continueBlockedCancelButton.Text = ResolveVisibleText("ui.menu.continue_blocked.cancel");
        }
        if (_continueBlockedReturnButton is not null)
        {
            _continueBlockedReturnButton.Text = ResolveVisibleText("ui.menu.continue_blocked.return_to_menu");
        }
    }

    private static string ResolveVisibleText(string keyOrText)
    {
        if (string.IsNullOrWhiteSpace(keyOrText))
        {
            return string.Empty;
        }

        var fallback = ResolveTextFromTranslationFiles(keyOrText);
        if (!string.Equals(fallback, keyOrText, StringComparison.Ordinal))
        {
            return fallback;
        }

        var localized = TranslationServer.Translate(keyOrText);
        if (!string.Equals(localized, keyOrText, StringComparison.Ordinal))
        {
            return localized;
        }

        return fallback;
    }

    private static string ResolveTextFromTranslationFiles(string keyOrText)
    {
        _menuTextFallbacks ??= LoadMenuTextFallbacks();
        if (_menuTextFallbacks.TryGetValue(keyOrText, out var value) && !string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        return keyOrText;
    }

    private static Dictionary<string, string> LoadMenuTextFallbacks()
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        var locale = TranslationServer.GetLocale();
        var preferred = NormalizeLocale(locale).StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? "res://../Game.Godot/Translations/zh-CN.csv"
            : "res://../Game.Godot/Translations/en.csv";
        var path = preferred;
        if (!FileAccess.FileExists(path))
        {
            path = "res://Game.Godot/Translations/en.csv";
        }
        if (!FileAccess.FileExists(path))
        {
            path = "res://../Game.Godot/Translations/en.csv";
        }

        if (!FileAccess.FileExists(path))
        {
            return map;
        }

        using var file = FileAccess.Open(path, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            return map;
        }

        var raw = file.GetAsText();
        foreach (var line in raw.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrWhiteSpace(trimmed) || trimmed.StartsWith("key,value", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var sep = trimmed.IndexOf(',');
            if (sep <= 0 || sep >= trimmed.Length - 1)
            {
                continue;
            }

            var key = trimmed[..sep].Trim();
            var value = trimmed[(sep + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(key) && !string.IsNullOrWhiteSpace(value))
            {
                map[key] = value;
            }
        }

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

    private void Publish(string type, string source, string dataJson = "{}")
    {
        var bus = GetNodeOrNull<EventBusAdapter>("/root/EventBus");
        bus?.PublishSimple(type, source, dataJson);
    }

    private void RefreshContinueAvailability()
    {
        _btnContinue.Disabled = !HasValidAutosave();
    }

    private bool HasValidAutosave()
    {
        return EvaluateContinueLoad().ContinueAllowed;
    }

    private static bool HasRequiredString(JsonElement root, string propertyName)
    {
        return root.TryGetProperty(propertyName, out var value)
            && value.ValueKind == JsonValueKind.String
            && !string.IsNullOrWhiteSpace(value.GetString());
    }

    private static bool HasRequiredDateTimeOffset(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        return DateTimeOffset.TryParse(value.GetString(), out _);
    }

    private void OnNewRunPressed()
    {
        HideContinueBlockedDialog(clearMessage: false);
        if (HasValidAutosave() && _overwriteConfirmDialog is not null)
        {
            _lastDialogFocusPreferenceForTest = "cancel";
            _overwriteConfirmDialog.PopupCentered();
            CallDeferred(MethodName.FocusOverwriteCancelButton);

            return;
        }

        StartNewRun();
    }

    private void OnOverwriteConfirmed()
    {
        StartNewRun();
    }

    private void OnOverwriteCanceled()
    {
        // Cancel keeps autosave and menu state unchanged.
    }

    private void FocusOverwriteCancelButton()
    {
        if (_overwriteConfirmDialog?.GetCancelButton() is BaseButton cancelButton)
        {
            cancelButton.GrabFocus();
        }
    }

    private void StartNewRun()
    {
        HideContinueBlockedDialog(clearMessage: true);
        Publish("ui.menu.new_run", "ui");
        Publish("ui.menu.start", "ui");
        Publish(EventTypes.RunStarted, "ui");
        HideMenu();
    }

    private void OnContinuePressed()
    {
        var validation = EvaluateContinueLoad();
        if (!validation.ContinueAllowed)
        {
            ShowContinueBlockedState(validation);
            Publish(EventTypes.RunContinueBlocked, "ui", BuildContinueBlockedPayload(validation));
            RefreshContinueAvailability();
            return;
        }

        HideContinueBlockedDialog(clearMessage: true);
        Publish("ui.menu.continue", "ui");
        Publish(EventTypes.RunResumed, "ui");
        HideMenu();
    }

    private void OnQuitPressed()
    {
        _quitRequested = true;
        Publish("ui.menu.quit", "ui");
        _quitIntentReachedForTest = true;
        if (_hasQuitRequestCallbackForTest)
        {
            _quitRequestCallbackForTest.Call();
            return;
        }

        if (!_disableQuitForTests)
        {
            GetTree().Quit();
        }
    }

    private ContinueLoadValidationResult EvaluateContinueLoad()
    {
        if (_autosaveAvailableOverride.HasValue)
        {
            return _autosaveAvailableOverride.Value
                ? new ContinueLoadValidationResult(true, null, null)
                : new ContinueLoadValidationResult(false, "missing_save", "Continue is unavailable because no save was found.");
        }

        using var file = FileAccess.Open(AutosavePath, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            return new ContinueLoadValidationResult(false, "missing_save", "Continue is unavailable because no save was found.");
        }

        var text = file.GetAsText().Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return new ContinueLoadValidationResult(false, "missing_save", "Continue is unavailable because no save was found.");
        }

        try
        {
            using var document = JsonDocument.Parse(text, AutosaveJsonOptions);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                return new ContinueLoadValidationResult(false, "invalid_integrity", "Continue is unavailable because save integrity validation failed.");
            }

            if (!HasRequiredString(root, "run_id")
                || !HasRequiredString(root, "save_point_id")
                || !HasRequiredString(root, "schema_version")
                || !HasRequiredString(root, "state_json")
                || !HasRequiredString(root, "integrity_hash")
                || !HasRequiredDateTimeOffset(root, "saved_at"))
            {
                return new ContinueLoadValidationResult(false, "invalid_integrity", "Continue is unavailable because save integrity validation failed.");
            }

            var schemaVersion = root.GetProperty("schema_version").GetString();
            if (!IsSupportedSchemaVersion(schemaVersion))
            {
                return new ContinueLoadValidationResult(false, "migration_failed", "Continue is unavailable because save migration failed.");
            }

            var stateJson = root.GetProperty("state_json").GetString() ?? string.Empty;
            var integrityHash = root.GetProperty("integrity_hash").GetString();
            var expectedIntegrityHash = ComputeIntegrityHash(stateJson);
            if (!string.Equals(integrityHash, expectedIntegrityHash, StringComparison.Ordinal))
            {
                return new ContinueLoadValidationResult(false, "invalid_integrity", "Continue is unavailable because save integrity validation failed.");
            }

            return new ContinueLoadValidationResult(true, null, null);
        }
        catch (JsonException)
        {
            return new ContinueLoadValidationResult(false, "invalid_integrity", "Continue is unavailable because save integrity validation failed.");
        }
    }

    private static bool IsSupportedSchemaVersion(string? schemaVersion)
    {
        if (string.IsNullOrWhiteSpace(schemaVersion))
        {
            return false;
        }

        var parts = schemaVersion.Split('.');
        if (parts.Length == 0 || !int.TryParse(parts[0], out var major))
        {
            return false;
        }

        return major == SupportedSchemaMajor;
    }

    private static string ComputeIntegrityHash(string content)
    {
        var bytes = Encoding.UTF8.GetBytes(content);
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }

    private void ShowContinueBlockedState(ContinueLoadValidationResult validation)
    {
        if (_continueBlockedDialog is null || _continueBlockedMessageLabel is null)
        {
            return;
        }

        _continueBlockedMessageLabel.Text = BuildContinueBlockedMessage(validation);
        _continueBlockedDialog.Visible = true;
    }

    private void HideContinueBlockedDialog(bool clearMessage)
    {
        if (_continueBlockedDialog is not null)
        {
            _continueBlockedDialog.Visible = false;
        }

        if (clearMessage && _continueBlockedMessageLabel is not null)
        {
            _continueBlockedMessageLabel.Text = string.Empty;
        }
    }

    private static string BuildContinueBlockedMessage(ContinueLoadValidationResult validation)
    {
        var blockedStatePrefix = ResolveVisibleText("continue.blocked_state");
        if (string.IsNullOrWhiteSpace(blockedStatePrefix) || string.Equals(blockedStatePrefix, "continue.blocked_state", StringComparison.Ordinal))
        {
            blockedStatePrefix = "Continue is currently blocked.";
        }

        var reasonMessage = validation.ErrorCode switch
        {
            "missing_save" => "No save was found.",
            "migration_failed" => "Save migration failed. Start a new run or return to the menu; mid-combat resume is not supported.",
            _ => "Save integrity validation failed. Start a new run or return to the menu."
        };

        var baseMessage = $"{blockedStatePrefix} {reasonMessage}".Trim();
        if (!string.IsNullOrWhiteSpace(validation.ErrorMessage)
            && !baseMessage.Contains(validation.ErrorMessage, StringComparison.OrdinalIgnoreCase))
        {
            return string.Concat(baseMessage, " ", validation.ErrorMessage);
        }

        return baseMessage;
    }

    private static string BuildContinueBlockedPayload(ContinueLoadValidationResult validation)
    {
        var payload = new Dictionary<string, string>
        {
            ["reason_code"] = validation.ErrorCode ?? "continue_blocked",
            ["message"] = BuildContinueBlockedMessage(validation)
        };
        return JsonSerializer.Serialize(payload);
    }

    private void OnContinueBlockedNewRunPressed()
    {
        StartNewRun();
    }

    private void OnContinueBlockedDismissed()
    {
        HideContinueBlockedDialog(clearMessage: false);
        ShowMenu();
    }
}

