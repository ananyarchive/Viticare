"use client";

import { useEffect, useState } from "react";

const API_BASE = "http://localhost:8000";

interface Patient {
  id: string;
  excluded_images: string[];
}

interface Measurement {
  area_px: number;
  bounding_width_px: number;
  bounding_height_px: number;
}

interface ProgressStats {
  region_area_px: number;
  mean_brightness_change: number;
  repigmented_px: number;
  progressed_px: number;
  repigmentation_pct_of_region: number;
  reference_frame: string;
}

interface TimelineEntry {
  source_file: string;
  raw_image_url: string;
  outlined_image_url: string;
  mask_image_url: string;
  lesion_area_pct_of_image: number;
  num_regions_detected: number;
  measurements: Measurement[];
  heatmap_image_url?: string;
  progress_stats?: ProgressStats;
}

interface TimelineResponse {
  patient_id: string;
  timepoint_count: number;
  timeline: TimelineEntry[];
}

export default function Dashboard() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/patients`)
      .then((res) => res.json())
      .then((data) => {
        const withImages = data.patients.filter(
          (p: Patient) => p.excluded_images.length < 5
        );
        setPatients(withImages);
        if (withImages.length > 0) setSelectedId(withImages[0].id);
      })
      .catch(() => setError("Could not reach the backend. Is uvicorn running?"));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    fetch(`${API_BASE}/patients/${selectedId}/timeline`)
      .then((res) => res.json())
      .then((data) => {
        setTimeline(data);
        setLoading(false);
      })
      .catch(() => {
        setError("Could not load timeline for this patient.");
        setLoading(false);
      });
  }, [selectedId]);

  const latestWithProgress = timeline?.timeline
    .filter((t) => t.progress_stats)
    .slice(-1)[0];

  return (
    <div className="min-h-screen bg-[#F6F2EA] text-[#332C24]">
      <header className="border-b border-[#E4D9C3] bg-[#FBF9F4] px-10 py-7">
        <h1 className="font-[family-name:var(--font-display)] text-[28px] italic tracking-tight text-[#4B5A3E]">
          VitiCare
        </h1>
        <p className="text-[13px] text-[#9C8F79] mt-1 tracking-wide uppercase">
          Longitudinal Vitiligo Progress Tracking
        </p>
      </header>

      <div className="flex">
        <aside className="w-60 border-r border-[#E4D9C3] bg-[#FBF9F4] min-h-[calc(100vh-97px)] py-6">
          <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-[#B0A38B] mb-3 px-6">
            Patients — {patients.length}
          </p>
          <div className="space-y-0.5 px-3">
            {patients.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedId(p.id)}
                className={
                  selectedId === p.id
                    ? "w-full text-left px-3.5 py-2 rounded-md text-[13.5px] transition-colors bg-[#DFE5D3] text-[#42502F] font-medium"
                    : "w-full text-left px-3.5 py-2 rounded-md text-[13.5px] transition-colors hover:bg-[#F1ECE0] text-[#5C5245]"
                }
              >
                Patient {p.id}
              </button>
            ))}
          </div>
        </aside>

        <main className="flex-1 px-10 py-8">
          {error && (
            <div className="bg-[#F5E6D8] border border-[#E0BFA0] text-[#8A5A2E] px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {!error && loading && (
            <p className="text-[#9C8F79] text-sm">Loading timeline…</p>
          )}

          {!error && !loading && timeline && (
            <div className="space-y-10 max-w-5xl">
              <div className="bg-[#FBF9F4] border border-[#E4D9C3] rounded-xl px-7 py-6">
                <div className="flex items-baseline justify-between border-b border-[#EDE6D8] pb-4 mb-5">
                  <h2 className="font-[family-name:var(--font-display)] text-xl text-[#3A4530]">
                    Patient {timeline.patient_id}
                  </h2>
                  <span className="text-[11px] uppercase tracking-wide text-[#B0A38B]">
                    {timeline.timepoint_count} timepoints
                  </span>
                </div>

                {latestWithProgress?.progress_stats ? (
                  <div className="grid grid-cols-3 gap-px bg-[#E4D9C3] rounded-lg overflow-hidden">
                    <div className="bg-[#FBF9F4] px-5 py-5 text-center">
                      <p className="font-[family-name:var(--font-display)] text-[30px] leading-none text-[#4B5A3E]">
                        {latestWithProgress.progress_stats.repigmentation_pct_of_region.toFixed(1)}
                        <span className="text-[18px]">%</span>
                      </p>
                      <p className="text-[11px] uppercase tracking-wide text-[#9C8F79] mt-2">
                        Repigmentation
                      </p>
                    </div>
                    <div className="bg-[#FBF9F4] px-5 py-5 text-center">
                      <p className="font-[family-name:var(--font-display)] text-[30px] leading-none text-[#8A6E4E]">
                        {latestWithProgress.progress_stats.mean_brightness_change.toFixed(1)}
                      </p>
                      <p className="text-[11px] uppercase tracking-wide text-[#9C8F79] mt-2">
                        Brightness Δ
                      </p>
                    </div>
                    <div className="bg-[#FBF9F4] px-5 py-5 text-center">
                      <p className="font-[family-name:var(--font-display)] text-[30px] leading-none text-[#6B6355]">
                        {timeline.timepoint_count}
                      </p>
                      <p className="text-[11px] uppercase tracking-wide text-[#9C8F79] mt-2">
                        Photos Tracked
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-[13px] text-[#9C8F79]">
                    Not enough comparable timepoints yet to compute a trend.
                  </p>
                )}
              </div>

              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-[#B0A38B] mb-4">
                  Timeline
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                  {timeline.timeline.map((entry) => (
                    <div
                      key={entry.source_file}
                      className="bg-[#FBF9F4] border border-[#E4D9C3] rounded-xl overflow-hidden"
                    >
                      <img
                        src={`${API_BASE}${entry.heatmap_image_url || entry.outlined_image_url}`}
                        alt={entry.source_file}
                        className="w-full h-44 object-cover"
                      />
                      <div className="px-4 py-3.5 border-t border-[#EDE6D8]">
                        <p className="text-[11px] text-[#B0A38B] mb-1.5 font-mono">
                          {entry.source_file}
                        </p>
                        {entry.progress_stats ? (
                          <p className="text-[13.5px] text-[#4B5A3E] font-medium">
                            {entry.progress_stats.repigmentation_pct_of_region.toFixed(1)}% repigmented
                          </p>
                        ) : (
                          <p className="text-[13.5px] text-[#9C8F79] italic">
                            Reference frame
                          </p>
                        )}
                        <p className="text-[11px] text-[#B0A38B] mt-1">
                          {entry.num_regions_detected} region(s) detected
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
