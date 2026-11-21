cmake_minimum_required(VERSION 3.24)
project(WinyunqCodeSytle LANGUAGES CXX)

include(FetchContent)
FetchContent_Declare(json
    URL https://raw.githubusercontent.com/nlohmann/json/v3.11.3/single_include/nlohmann/json.hpp
    URL_HASH SHA256=9bea4c8066ef4a1c206b2be5a36302f8926f7fdc6087af5d20b417d0cf103ea6
    DOWNLOAD_NO_EXTRACT TRUE)
FetchContent_MakeAvailable(json)

add_library(pugixml STATIC libs/pugixml/pugixml.cpp)
add_library(pugixml::pugixml ALIAS pugixml)
target_include_directories(pugixml PUBLIC libs/pugixml)
set_target_properties(pugixml PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(WinyunqCodeSytleCore
    Source/Authorization/SourceWriteAuthorization.cpp
    Source/Configure/NativeProject.cpp
    Source/Configure/GenerateWebsite.cpp
    Source/Read/FindSymbols.cpp
    Source/Read/ReadDeclaration.cpp
    Source/Read/ReadDefinition.cpp
    Source/Read/ReadDocumentation.cpp
    Source/Read/ReadTypeMembers.cpp
    Source/Read/FindReferences.cpp
    Source/Write/EditDocumentation.cpp
    Source/Write/EditFunction.cpp
    Source/Write/EditSource.cpp
    Source/Delete/DeleteDocumentation.cpp
    Source/Delete/DeleteSymbols.cpp
    Source/Delete/DeleteCodeFragment.cpp)
target_compile_features(WinyunqCodeSytleCore PUBLIC cxx_std_17)
target_include_directories(WinyunqCodeSytleCore PUBLIC Source)
target_link_libraries(WinyunqCodeSytleCore PUBLIC pugixml::pugixml)
if(WIN32)
    target_link_libraries(WinyunqCodeSytleCore PRIVATE bcrypt)
else()
    find_package(OpenSSL REQUIRED COMPONENTS Crypto)
    target_link_libraries(WinyunqCodeSytleCore PRIVATE OpenSSL::Crypto)
endif()
if(MSVC)
    set_source_files_properties(Source/Configure/GenerateWebsite.cpp PROPERTIES COMPILE_OPTIONS /utf-8)
endif()
set(WebsiteAssets "${CMAKE_CURRENT_SOURCE_DIR}/Source/Configure/WebsiteAssets")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${WebsiteAssets}/site.css" "${WebsiteAssets}/site.js")
file(READ "${WebsiteAssets}/site.css" WebsiteStyle)
file(READ "${WebsiteAssets}/site.js" WebsiteScript)
configure_file(Source/Configure/WebsiteAssets/WebsiteStyle.h.in WebsiteStyle.h @ONLY)
target_include_directories(WinyunqCodeSytleCore PRIVATE "${CMAKE_CURRENT_BINARY_DIR}" "${json_SOURCE_DIR}")

add_executable(WinyunqCodeSytle Source/Configure/StartServer.cpp)
target_include_directories(WinyunqCodeSytle PRIVATE "${json_SOURCE_DIR}")
target_link_libraries(WinyunqCodeSytle PRIVATE WinyunqCodeSytleCore)
if(MINGW)
    target_link_options(WinyunqCodeSytle PRIVATE -static)
endif()
install(TARGETS WinyunqCodeSytle RUNTIME DESTINATION bin)

if(WIN32 AND MSVC)
    add_executable(UnrealMcpAuthorization Source/Authorization/WindowsNotification.cpp)
    target_compile_features(UnrealMcpAuthorization PRIVATE cxx_std_20)
    target_compile_options(UnrealMcpAuthorization PRIVATE /utf-8)
    target_include_directories(UnrealMcpAuthorization PRIVATE
        "$ENV{WindowsSdkDir}/Include/$ENV{WindowsSDKVersion}/cppwinrt" "${json_SOURCE_DIR}")
    target_link_libraries(UnrealMcpAuthorization PRIVATE runtimeobject shell32 ole32 oleaut32 propsys comctl32)
    install(TARGETS UnrealMcpAuthorization RUNTIME DESTINATION bin)
endif()
