import type { JsonSchema, UISchemaElement } from "@jsonforms/core";

import awardTemplate from "@/config/task-editor-schemas/Award.json";
import closeDownTemplate from "@/config/task-editor-schemas/CloseDown.json";
import fightTemplate from "@/config/task-editor-schemas/Fight.json";
import infrastTemplate from "@/config/task-editor-schemas/Infrast.json";
import mallTemplate from "@/config/task-editor-schemas/Mall.json";
import recruitTemplate from "@/config/task-editor-schemas/Recruit.json";
import startUpTemplate from "@/config/task-editor-schemas/StartUp.json";

export type TaskEditorTemplate = {
  schema: JsonSchema;
  general: string[];
  advanced?: string[];
};

export type TaskEditorSchema = {
  schema: JsonSchema;
  general: UISchemaElement;
  advanced?: UISchemaElement;
  generalKeys: string[];
  advancedKeys: string[];
};

const taskTemplates: Record<string, TaskEditorTemplate> = {
  Award: awardTemplate as TaskEditorTemplate,
  CloseDown: closeDownTemplate as TaskEditorTemplate,
  Fight: fightTemplate as TaskEditorTemplate,
  Infrast: infrastTemplate as TaskEditorTemplate,
  Mall: mallTemplate as TaskEditorTemplate,
  Recruit: recruitTemplate as TaskEditorTemplate,
  StartUp: startUpTemplate as TaskEditorTemplate
};

export function schemaForTaskType(type: string): TaskEditorSchema | undefined {
  const template = taskTemplates[type];
  if (!template) return undefined;

  const generalKeys = template.general || [];
  const advancedKeys = template.advanced || [];
  return {
    schema: template.schema,
    general: vertical(generalKeys),
    advanced: advancedKeys.length > 0 ? vertical(advancedKeys) : undefined,
    generalKeys,
    advancedKeys
  };
}

function vertical(keys: string[]): UISchemaElement {
  return {
    type: "VerticalLayout",
    elements: keys.map((key) => ({ type: "Control", scope: `#/properties/${key}` }))
  };
}
