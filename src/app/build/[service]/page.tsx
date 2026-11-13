import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { BuildFlow } from "@/components/build-flow";
import { getService, SERVICES } from "@/lib/services";

type Props = { params: Promise<{ service: string }> };

export function generateStaticParams() {
  return SERVICES.map((s) => ({ service: s.id }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const service = getService((await params).service);
  return service ? { title: `Build: ${service.name}`, description: service.tagline } : { title: "Not found" };
}

export default function BuildPage({ params }: Props) {
  return (
    <Suspense fallback={<div className="mt-10 h-96 animate-pulse rounded-3xl bg-surface" />}>
      <Loader params={params} />
    </Suspense>
  );
}

async function Loader({ params }: Props) {
  const service = getService((await params).service);
  if (!service) notFound();
  return <BuildFlow service={service} />;
}
