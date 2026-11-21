#pragma once

#include "Read/FindSymbols.h"
#include <json.hpp>

namespace WinyunqCodeSytle
{
nlohmann::json ReadDocumentation(const Symbol& symbol);
}
