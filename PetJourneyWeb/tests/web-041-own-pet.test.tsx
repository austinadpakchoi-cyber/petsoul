import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { SessionState } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { OnboardingPage } from "@/features/pets/pages";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

const owner: SessionState = {
  authenticated: true,
  user: { user_id: "u-own", username: "owner", display_name: null, auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "needs_companion", pet_id: null, home_id: null, reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: null },
};

describe("own-pet introduction", () => {
  it("keeps photo optional and sends the chosen species through the existing creation service", async () => {
    const createOwn = vi.fn(() => new Promise<never>(() => undefined));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const services = new Proxy({
      session: { current: async () => owner },
      pets: { createOwn },
    } as unknown as ServiceMap, {
      get(target, prop: string) {
        if (prop in target) return target[prop as keyof ServiceMap];
        throw new Error(`unexpected service ${prop}`);
      },
    });
    const page = render(
      <QueryClientProvider client={queryClient}>
        <ServicesProvider services={services}>
          <MemoryRouter initialEntries={["/onboarding"]}><OnboardingPage /></MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    const view = within(page.container);
    expect(await view.findByRole("heading", { name: "这是 TA。" })).toBeTruthy();
    expect(view.getByLabelText("上传 TA 的照片")).toBeTruthy();
    expect(page.container.querySelectorAll(".ps-species-art")).toHaveLength(7);
    expect(view.getByRole("link", { name: /去认识他们/ }).getAttribute("href")).toBe("/adopt");
    fireEvent.change(view.getByLabelText("上传 TA 的照片"), { target: { files: [new File(["x"], "not-a-photo.gif", { type: "image/gif" })] } });
    expect(view.getByRole("alert").textContent).toContain("只支持 JPEG");
    fireEvent.change(view.getByLabelText("上传 TA 的照片"), { target: { files: [] } });
    fireEvent.change(view.getByLabelText("02 / TA 叫什么名字？"), { target: { value: "团子" } });
    fireEvent.click(view.getByRole("radio", { name: "狗" }));
    fireEvent.click(view.getByRole("button", { name: "继续，去见接待员" }));
    await waitFor(() => expect(createOwn).toHaveBeenCalledWith({ name: "团子", species: "dog", photo: null, householdId: undefined }, expect.any(String)));
    page.unmount();
  });
});
