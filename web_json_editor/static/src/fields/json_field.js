/** @odoo-module */

import {
  Component,
  onMounted,
  onWillUnmount,
  useEffect,
  useRef,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Simple JSON formatter for display mode
 * @param {*} value - Value to format as JSON
 * @returns {String} Formatted JSON string
 */
export function formatJSON(value) {
  if (!value) return "";
  try {
    const parsed = typeof value === "string" ? JSON.parse(value) : value;
    return JSON.stringify(parsed, null, 2);
  } catch (e) {
    console.error("Error formatting JSON:", e);
    return String(value);
  }
}

/**
 * JSON Editor Field Component
 */
export class JsonEditorField extends Component {
  setup() {
    this.editorRef = useRef("editor");
    this.editor = null;
    this._updateTimer = null;
    // Track whether the editor has focus to prevent external updates
    // from resetting cursor position while user is typing.
    this._hasFocus = false;

    onMounted(() => this.initEditor());
    onWillUnmount(() => this.destroyEditor());

    // Update editor when field value changes externally
    useEffect(() => {
      let value = this.props.record.data[this.props.name];

      // Never overwrite the editor while the user is actively editing
      if (
        this.editor &&
        !this._hasFocus &&
        !this.props.record.isFieldInvalid(this.props.name)
      ) {
        if (!value) {
          value = {};
        } else if (typeof value === "string") {
          try {
            value = JSON.parse(value);
          } catch (e) {
            value = {};
          }
        }

        try {
          const currentValue = this.editor.get();
          if (JSON.stringify(currentValue) !== JSON.stringify(value)) {
            this.editor.set(value);
          }
        } catch (e) {
          this.editor.set(value);
        }
      }
    });
  }

  initEditor() {
    if (!this.editorRef.el) return;

    const options = {
      mode: this.props.readonly ? "view" : "code",
      modes: ["code", "view"],
      search: true,
      history: true,
      navigationBar: true,
      statusBar: true,
      mainMenuBar: true,
      onChange: () => {
        if (!this.props.readonly) {
          this._scheduleUpdate();
        }
      },
    };

    if (this.props.nodeOptions) {
      const editorOptions = this.props.nodeOptions.editor_options || {};
      Object.assign(options, editorOptions);
    }

    if (this.props.nodeOptions?.schema) {
      try {
        options.schema =
          typeof this.props.nodeOptions.schema === "string"
            ? JSON.parse(this.props.nodeOptions.schema)
            : this.props.nodeOptions.schema;
      } catch (e) {
        console.warn("Invalid JSON schema:", e);
      }
    }

    this.editor = new JSONEditor(this.editorRef.el, options);

    if (this.editor.aceEditor) {
      this.editor.aceEditor.getSession().setUseWorker(false);

      // Track focus via the underlying Ace editor so we know when the
      // user is actively typing and should not have their cursor reset.
      this.editor.aceEditor.on("focus", () => {
        this._hasFocus = true;
      });
      this.editor.aceEditor.on("blur", () => {
        this._hasFocus = false;
        // Flush any pending update immediately on blur
        this._flushUpdate();
      });
    }

    let value = this.props.record.data[this.props.name];
    if (!value) {
      value = {};
    } else if (typeof value === "string") {
      try {
        value = JSON.parse(value);
      } catch (e) {
        value = {};
      }
    }
    this.editor.set(value);
  }

  formatValue() {
    const value = this.props.record.data[this.props.name];
    if (!value) return "{}";
    if (typeof value === "string") {
      try {
        return formatJSON(JSON.parse(value));
      } catch (e) {
        return value;
      }
    }
    return formatJSON(value);
  }

  /**
   * Debounce record updates so we don't call record.update() on every
   * keystroke, which would trigger re-renders and cursor resets.
   */
  _scheduleUpdate() {
    if (this._updateTimer) {
      clearTimeout(this._updateTimer);
    }
    this._updateTimer = setTimeout(() => {
      this._updateTimer = null;
      this._flushUpdate();
    }, 300);
  }

  _flushUpdate() {
    if (this._updateTimer) {
      clearTimeout(this._updateTimer);
      this._updateTimer = null;
    }
    if (!this.editor) return;

    let jsonValue;
    try {
      jsonValue = this.editor.get();
    } catch (e) {
      // Editor content is not valid JSON yet — skip update
      return;
    }

    if (this.props.record.fields[this.props.name].type === "json") {
      this.props.record.update({ [this.props.name]: jsonValue });
    } else {
      this.props.record.update({ [this.props.name]: JSON.stringify(jsonValue) });
    }
  }

  destroyEditor() {
    if (this._updateTimer) {
      clearTimeout(this._updateTimer);
      this._updateTimer = null;
    }
    if (this.editor) {
      this.editor.destroy();
      this.editor = null;
    }
  }
}

JsonEditorField.template = "web_json_editor.JsonEditorField";
JsonEditorField.props = {
  ...standardFieldProps,
  readonly: { type: Boolean, optional: true },
};

registry.category("fields").add("json_editor", {
  component: JsonEditorField,
  supportedTypes: ["text", "char", "json"],
});
