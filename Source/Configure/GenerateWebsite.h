#pragma once

#include "Configure/NativeProject.h"
#include <json.hpp>

namespace pugi { class xml_node; }

namespace WinyunqCodeSytle
{
/// Export API documentation through the shared website renderer.
nlohmann::json GenerateWebsite(NativeProject& project, const nlohmann::json& profile, const std::string& audience);
bool Published(pugi::xml_node node);
}
