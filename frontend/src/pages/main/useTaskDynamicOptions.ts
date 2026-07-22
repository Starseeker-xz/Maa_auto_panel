import React from "react";

import { getInfrastFileOptions, getInfrastPlanOptions, getMaaStages } from "@/lib/api";
import type { DynamicOption, TaskItem } from "@/lib/types";

export function useTaskDynamicOptions(selectedTaskItem: TaskItem | undefined, params: Record<string, unknown>) {
  const [dynamicOptions, setDynamicOptions] = React.useState<Record<string, DynamicOption[]>>({});
  const fightClient = typeof params.client_type === "string" ? params.client_type : "Bilibili";
  const infrastFilename = typeof params.filename === "string" ? params.filename : "";

  React.useEffect(() => {
    let cancelled = false;

    async function loadOptions() {
      const next: Record<string, DynamicOption[]> = {};
      try {
        if (selectedTaskItem?.type === "Fight") {
          const stages = await getMaaStages(fightClient, true);
          next["fight-stages"] = stages.stages
            .filter((stage) => stage.is_open_or_will_open !== false)
            .map((stage) => ({
              value: stage.value,
              label: stage.display || stage.value || "当前/上次"
            }));
        }
        if (selectedTaskItem?.type === "Infrast") {
          const files = await getInfrastFileOptions();
          next["infrast-files"] = files.options;
          next["infrast-plans"] = infrastFilename ? (await getInfrastPlanOptions(infrastFilename)).options : [];
        }
      } catch {
        // Keep the editor usable with free-text fallback if option APIs fail.
      }
      if (!cancelled) setDynamicOptions(next);
    }

    loadOptions();
    return () => {
      cancelled = true;
    };
  }, [fightClient, infrastFilename, selectedTaskItem?.type]);

  return dynamicOptions;
}
