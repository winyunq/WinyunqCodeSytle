#pragma once
#include <algorithm>
#include <cstddef>
#include <vector>

// A portable, instrumented test double; not the UE runtime or its ABI.
namespace Fixture {
inline std::size_t MembershipQueries = 0;
inline std::size_t SelectionCopies = 0;

struct EntityList {
    std::vector<int> Values;
    int Num() const { return static_cast<int>(Values.size()); }
};

class Selection {
public:
    explicit Selection(int WorldSize) {
        for (int Index = 0; Index < WorldSize; ++Index) WorldEntities.push_back(Index);
    }
    void SetSelection(int Count) {
        SelectedEntities.Values.clear();
        for (int Index = 0; Index < Count; ++Index) SelectedEntities.Values.push_back(Index * 2);
    }
    /** @brief Zero-copy native view for per-frame systems.
     * @return Existing selection owned by this subsystem; do not maintain another selection list.
     */
    const EntityList& GetSelectedEntitiesView() const { return SelectedEntities; }
    /** @brief Safe copy for callers requiring their own container. */
    EntityList GetSelectedEntities() const { ++SelectionCopies; return SelectedEntities; }
    /** @brief All world entities, not only the current selection. */
    const std::vector<int>& GetAllEntities() const { return WorldEntities; }
    bool IsEntitySelected(int Entity) const {
        ++MembershipQueries;
        return std::find(SelectedEntities.Values.begin(), SelectedEntities.Values.end(), Entity)
            != SelectedEntities.Values.end();
    }
private:
    EntityList SelectedEntities;
    std::vector<int> WorldEntities;
};

class HUD {
public:
    /** @brief Read the current number of selected entities without copying or scanning the world.
     * @param ExistingSelection The authoritative subsystem already held by the HUD.
     * @return Current selection count.
     */
    int GetSelectedCount(const Selection& ExistingSelection) const;
};
}
