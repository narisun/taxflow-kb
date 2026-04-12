"use client";

import { W2Form } from "./w2-form";
import { Form1099Int } from "./form-1099-int";
import { GenericForm } from "./generic-form";

/* eslint-disable @typescript-eslint/no-explicit-any */
export function FormRenderer({
  formType,
  data,
}: {
  formType: string;
  data: any;
}) {
  switch (formType) {
    case "W-2":
      return <W2Form data={data} />;
    case "1099-INT":
      return <Form1099Int data={data} />;
    case "1098":
      return <GenericForm formType="1098" data={data} />;
    default:
      return <GenericForm formType={formType} data={data} />;
  }
}
