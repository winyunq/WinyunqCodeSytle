#include "Selection.h"
int Fixture::HUD::GetSelectedCount(const Fixture::Selection& ExistingSelection) const
{
    return ExistingSelection.GetSelectedEntitiesView().Num();
}
