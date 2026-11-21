#include <windows.h>
#include <commctrl.h>
#include <shlobj.h>
#include <propkey.h>
#include <propvarutil.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Data.Xml.Dom.h>
#include <winrt/Windows.UI.Notifications.h>
#include <array>
#include <filesystem>
#include <fstream>
#include <future>
#include <json.hpp>
#include <iostream>
#include <string>

using namespace winrt;
using namespace Windows::UI::Notifications;

namespace {
constexpr auto AppId = L"Winyunq.UnrealEngineCPPCodingMCP.Authorization";

LRESULT CALLBACK SignatureWindow(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_NCCREATE) {
        const auto create = reinterpret_cast<CREATESTRUCTW*>(lparam);
        SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(create->lpCreateParams));
    } else if (message == WM_COMMAND && (LOWORD(wparam) == IDOK || LOWORD(wparam) == IDCANCEL)) {
        auto& answer = *reinterpret_cast<int*>(GetWindowLongPtrW(window, GWLP_USERDATA));
        answer = LOWORD(wparam) == IDOK ? 0 : 1;
        DestroyWindow(window);
        return 0;
    } else if (message == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

int ReviewSignature(const wchar_t* path) {
    std::ifstream input(std::filesystem::path(path), std::ios::binary);
    const auto review = nlohmann::json::parse(input);
    const INITCOMMONCONTROLSEX controls{sizeof(controls), ICC_LISTVIEW_CLASSES};
    check_bool(InitCommonControlsEx(&controls));
    const auto instance = GetModuleHandleW(nullptr);
    WNDCLASSW windowClass{};
    windowClass.lpfnWndProc = SignatureWindow;
    windowClass.hInstance = instance;
    windowClass.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32512));
    windowClass.hbrBackground = GetSysColorBrush(COLOR_BTNFACE);
    windowClass.lpszClassName = L"WinyunqSignatureReview";
    if (!RegisterClassW(&windowClass)) throw_last_error();
    int answer = 1;
    const auto window = CreateWindowExW(WS_EX_TOPMOST, windowClass.lpszClassName, L"确认公开 API 变更",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU, CW_USEDEFAULT, CW_USEDEFAULT, 900, 490,
        nullptr, nullptr, instance, &answer);
    check_pointer(window);
    const auto font = GetStockObject(DEFAULT_GUI_FONT);
    const auto control = [&](const wchar_t* type, const wchar_t* text, DWORD style, int left, int top,
                             int width, int height, int id = 0) {
        const auto handle = CreateWindowExW(0, type, text, WS_CHILD | WS_VISIBLE | style,
            left, top, width, height, window, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), instance, nullptr);
        check_pointer(handle);
        SendMessageW(handle, WM_SETFONT, reinterpret_cast<WPARAM>(font), TRUE);
        return handle;
    };
    const auto name = to_hstring(review.at("function").get<std::string>());
    control(L"STATIC", name.c_str(), SS_LEFT, 16, 13, 850, 22);
    auto description = review.value("brief", "");
    for (const auto& paragraph : review.value("details", nlohmann::json::array()))
        description += "\r\n" + paragraph.get<std::string>();
    const auto summary = to_hstring(description);
    control(L"EDIT", summary.c_str(), ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL | WS_TABSTOP,
            16, 41, 850, 100);
    const auto table = control(WC_LISTVIEWW, L"参数变更", LVS_REPORT | WS_BORDER | WS_TABSTOP | WS_VSCROLL,
                               16, 151, 850, 246);
    ListView_SetExtendedListViewStyle(table, LVS_EX_GRIDLINES | LVS_EX_FULLROWSELECT | LVS_EX_LABELTIP);
    const std::array<const wchar_t*, 3> labels{L"原参数", L"新参数", L"参数说明"};
    const std::array<int, 3> widths{220, 220, 385};
    for (int i = 0; i < 3; ++i) {
        LVCOLUMNW column{};
        column.mask = LVCF_TEXT | LVCF_WIDTH;
        column.pszText = const_cast<wchar_t*>(labels[i]);
        column.cx = widths[i];
        SendMessageW(table, LVM_INSERTCOLUMNW, i, reinterpret_cast<LPARAM>(&column));
    }
    int index = 0;
    for (const auto& row : review.at("rows")) {
        LVITEMW item{};
        item.mask = LVIF_TEXT;
        item.iItem = index++;
        const auto before = to_hstring(row.at("before").get<std::string>());
        item.pszText = const_cast<wchar_t*>(before.c_str());
        SendMessageW(table, LVM_INSERTITEMW, 0, reinterpret_cast<LPARAM>(&item));
        const auto after = to_hstring(row.at("after").get<std::string>());
        item.iSubItem = 1;
        item.pszText = const_cast<wchar_t*>(after.c_str());
        SendMessageW(table, LVM_SETITEMTEXTW, item.iItem, reinterpret_cast<LPARAM>(&item));
        const auto note = to_hstring(row.at("description").get<std::string>());
        item.iSubItem = 2;
        item.pszText = const_cast<wchar_t*>(note.c_str());
        SendMessageW(table, LVM_SETITEMTEXTW, item.iItem, reinterpret_cast<LPARAM>(&item));
    }
    control(L"BUTTON", L"批准变更", BS_PUSHBUTTON | WS_TABSTOP, 616, 412, 116, 32, IDOK);
    const auto reject = control(L"BUTTON", L"拒绝变更", BS_DEFPUSHBUTTON | WS_TABSTOP, 750, 412, 116, 32, IDCANCEL);
    ShowWindow(window, SW_SHOW);
    SetFocus(reject);
    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        if (!IsDialogMessageW(window, &message)) {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }
    return answer;
}

void RegisterShortcut() {
    PWSTR programs = nullptr;
    check_hresult(SHGetKnownFolderPath(FOLDERID_Programs, 0, nullptr, &programs));
    std::wstring shortcut = programs;
    CoTaskMemFree(programs);
    shortcut += L"\\Unreal C++ MCP.lnk";
    wchar_t executable[32768];
    const auto length = GetModuleFileNameW(nullptr, executable, ARRAYSIZE(executable));
    if (!length || length == ARRAYSIZE(executable)) throw_last_error();
    auto link = create_instance<IShellLinkW>(CLSID_ShellLink);
    check_hresult(link->SetPath(executable));
    auto properties = link.as<IPropertyStore>();
    PROPVARIANT value;
    check_hresult(InitPropVariantFromString(AppId, &value));
    const auto result = properties->SetValue(PKEY_AppUserModel_ID, value);
    PropVariantClear(&value);
    check_hresult(result);
    check_hresult(properties->Commit());
    check_hresult(link.as<IPersistFile>()->Save(shortcut.c_str(), TRUE));
}

int RequestWrite(const wchar_t* directory) {
    auto notifier = ToastNotificationManager::CreateToastNotifier(AppId);

    Windows::Data::Xml::Dom::XmlDocument xml;
    xml.LoadXml(L"<toast><visual><binding template='ToastGeneric'>"
            L"<text>允许 MCP 写入此目录？</text><text/>"
            L"</binding></visual><actions>"
            L"<action content='永久授权' arguments='always'/>"
            L"<action content='本次允许' arguments='allow'/>"
            L"<action content='拒绝' arguments='deny'/>"
            L"</actions><audio silent='true'/></toast>");
    xml.GetElementsByTagName(L"text").Item(1).InnerText(directory);

    std::promise<int> decision;
    auto result = decision.get_future();
    const auto resolve = [&](int answer) {
        try { decision.set_value(answer); }
        catch (const std::future_error&) {}
    };
    ToastNotification toast(xml);
    auto activated = toast.Activated(auto_revoke, [&](auto const&, auto const& data) {
        if (auto args = data.try_as<ToastActivatedEventArgs>()) {
            if (args.Arguments() == L"always") resolve(3);
            if (args.Arguments() == L"allow") resolve(0);
            if (args.Arguments() == L"deny") resolve(1);
        }
    });
    auto dismissed = toast.Dismissed(auto_revoke, [&](auto const&, auto const& args) {
        if (args.Reason() == ToastDismissalReason::UserCanceled) resolve(1);
    });
    auto failed = toast.Failed(auto_revoke, [&](auto const&, auto const&) { resolve(2); });
    notifier.Show(toast);
    const int answer = result.wait_for(std::chrono::seconds(90)) == std::future_status::ready
        ? result.get() : 1;
    notifier.Hide(toast);
    return answer;
}
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 2 && argc != 3) return 2;
    try {
        if (argc == 3 && std::wstring_view(argv[1]) == L"--signature")
            return ReviewSignature(argv[2]);
        if (argc != 2) return 2;
        init_apartment();
        check_hresult(SetCurrentProcessExplicitAppUserModelID(AppId));
        RegisterShortcut();
        return RequestWrite(argv[1]);
    } catch (const hresult_error& error) {
        std::cerr << to_string(error.message()) << '\n';
        return 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
