(() => {
  "use strict";
  const VARIABLES = {
  "packet": {
    "origins": [],
    "description": "비디오 압축 데이터를 담는 av.Packet입니다. 수신·디코딩·인코딩·송출 단계에서 사용하며 PTS·DTS·time_base·duration으로 시간 정보를 표현합니다."
  },
  "video_stream": {
    "origins": [],
    "description": "영상의 코덱·해상도·시간 기준을 가진 비디오 스트림 정보입니다."
  },
  "frame": {
    "origins": [
      {
        "step": "NvidiaDecode",
        "variable": "frame"
      }
    ],
    "description": "GPU에 저장된 영상 프레임입니다."
  },
  "pixel_format": {
    "origins": [
      {
        "step": "NvidiaDecode",
        "variable": "pixel_format"
      }
    ],
    "description": "프레임의 픽셀 형식입니다. NATIVE (보통 NV12)로 고정합니다."
  },
  "cuda_stream": {
    "origins": [
      {
        "step": "NvidiaDecode",
        "variable": "cuda_stream"
      }
    ],
    "description": "GPU 작업의 실행 순서를 관리하는 작업 큐인 torch.cuda.Stream 객체입니다. CPU가 GPU 연산을 요청한 뒤에도 연산은 비동기로 진행될 수 있으며, 같은 스트림의 작업은 등록 순서대로 실행됩니다. CudaAsync 내부에서는 작업자 스트림을 전달하고 결과 반영 시 원래 스트림을 복원합니다. TensorRT 전처리·직접 추론·후처리는 이 스트림을 사용합니다. 공유 배치 추론은 이 스트림의 입력 준비 이벤트를 내부 작업자 스트림에서 기다립니다."
  },
  "decoded_at": {
    "description": "디코딩 결과를 큐에 넣은 시각(perf_counter 기준, 초)입니다."
  },
  "processing_started_at": {
    "origins": [
      {
        "step": "NvidiaDecode",
        "variable": "processing_started_at"
      }
    ],
    "description": "디코딩 큐에서 프레임을 꺼내 후속 처리를 시작한 시각(perf_counter 기준, 초)입니다. 프레임 처리 시간 집계에 사용합니다."
  },
  "decode_dropped_frames": {
    "description": "디코딩 큐에서 폐기한 프레임의 누적 개수입니다."
  },
  "video_stream.codec_context.width": {
    "parent": "video_stream",
    "description": "영상 너비(픽셀)입니다. NV12 입력에서는 양의 짝수여야 합니다."
  },
  "video_stream.codec_context.height": {
    "parent": "video_stream",
    "description": "영상 높이(픽셀)입니다. NV12 입력에서는 양의 짝수여야 합니다."
  },
  "detections[id]": {
    "parent": "detections",
    "description": "설정한 모델 ID의 YOLO 검출 결과입니다. 추론을 건너뛴 프레임은 None입니다."
  },
  "model_input": {
    "origins": [],
    "description": "YoloInference가 허용하는 입력은 GPU 텐서 하나 또는 {입력 이름: GPU 텐서} 사전입니다. 텐서의 형상·자료형·입력 이름과 입력 개수는 선택한 backend와 모델의 요구사항에 맞아야 하며 텐서의 GPU는 설정한 gpu_id와 일치해야 합니다. 입력이 하나인 엔진에는 텐서 자체를 전달할 수 있고, 여러 입력은 이름별 사전으로 전달합니다."
  },
  "model_output": {
    "origins": [
      {
        "step": "YoloInference",
        "variable": "model_output"
      }
    ],
    "description": "YoloInference의 출력은 {출력 이름: GPU 텐서} 사전이며 받은 모든 입력을 실행합니다. 실행 간격은 EveryNFrames로 지정합니다. 출력 이름·텐서 형상·자료형은 선택한 backend와 모델에 따라 달라지므로 모든 모델에 공통된 텐서 형식은 없습니다."
  },
  "model_id": {
    "origins": [
      {
        "step": "YoloInference",
        "variable": "model_id"
      }
    ],
    "description": "설정한 모델 식별자입니다. 추론 단계에서 제공하며 후처리의 검출 결과 사전 키로 사용합니다."
  },
  "기존 컨텍스트 변수": {
    "description": "입력 컨텍스트를 그대로 전달하며 새 변수를 추가하지 않습니다."
  },
  "tensor_rt_transform": {
    "origins": [],
    "description": "원본 크기와 리사이즈·패딩·크롭 정보를 가진 ImageTransform입니다. 전처리에서 제공하며 후처리에서 검출 좌표를 원본 영상 좌표로 복원할 때 사용합니다."
  },
  "detections[model_id]": {
    "parent": "detections",
    "description": "boxes·names·orig_shape를 가진 결과입니다. 추론을 건너뛰면 해당 ID의 값은 None입니다."
  }
};

  const STEP_REFERENCE = [
  {
    "name": "NvidiaDecode",
    "group": "내장 Step",
    "description": "NVIDIA GPU에서 압축 패킷을 디코딩하고 프레임을 전달합니다.",
    "inputs": {
      "rows": [
        {
          "variable": "packet"
        },
        {
          "variable": "video_stream"
        }
      ],
      "text": ""
    },
    "outputs": {
      "rows": [
        {
          "variable": "frame"
        },
        {
          "variable": "pixel_format"
        },
        {
          "variable": "cuda_stream"
        },
        {
          "variable": "video_stream"
        },
        {
          "variable": "decoded_at"
        },
        {
          "variable": "processing_started_at"
        },
        {
          "variable": "decode_dropped_frames"
        }
      ],
      "text": ""
    }
  },
  {
    "name": "NvidiaEncode",
    "group": "내장 Step",
    "description": "GPU 프레임을 압축 비디오 패킷으로 인코딩합니다.",
    "inputs": {
      "rows": [
        {
          "variable": "frame"
        },
        {
          "variable": "pixel_format"
        },
        {
          "variable": "video_stream"
        },
        {
          "variable": "cuda_stream"
        },
        {
          "variable": "processing_started_at"
        }
      ],
      "text": ""
    },
    "outputs": {
      "rows": [
        {
          "variable": "packet"
        },
        {
          "variable": "video_stream"
        }
      ],
      "text": ""
    }
  },
  {
    "name": "YoloInference",
    "group": "내장 Step",
    "description": "선택한 backend로 GPU 입력 텐서를 실행하고 원시 GPU 출력을 전달합니다.",
    "inputs": {
      "rows": [
        {
          "variable": "model_input"
        },
        {
          "variable": "cuda_stream"
        }
      ],
      "text": ""
    },
    "outputs": {
      "rows": [
        {
          "variable": "model_output"
        },
        {
          "variable": "model_id"
        }
      ],
      "text": ""
    }
  },
  {
    "name": "EveryNFrames",
    "group": "내장 Step",
    "description": "첫 입력부터 N프레임마다 내부 Step 묶음을 실행하고 생략 입력은 그대로 전달합니다. 각 내부 단계는 입력 하나당 출력 하나를 반환해야 합니다.",
    "inputs": {"rows": [], "text": "내부 Step의 입력을 사용합니다."},
    "outputs": {"rows": [], "text": "선택 프레임은 내부 Step의 출력, 생략 프레임은 원본을 전달합니다."}
  },
  {
    "name": "CudaAsync",
    "group": "내장 Step",
    "description": "감싼 Step들을 작업 스레드에서 실행하고 제한 시간 내 결과를 반영합니다.",
    "inputs": {
      "rows": [
        {
          "variable": "cuda_stream"
        }
      ],
      "text": ""
    },
    "outputs": {
      "rows": [],
      "text": ""
    }
  },
  {
    "name": "TapSkipIfBusy",
    "group": "내장 Step",
    "description": "별도 스레드에 입력을 전달하면서 주 파이프라인을 계속 진행하고, 내부 작업이 실행 중이면 새 입력은 건너뜁니다. TapSkipIfBusy로 감싼 Step의 출력은 기존 파이프라인에 영향을 미치지 않도록 분리됩니다.",
    "inputs": {
      "rows": [],
      "text": ""
    },
    "outputs": {
      "rows": [],
      "text": ""
    }
  }
];

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function outputId(variable) {
    return "output-" + encodeURIComponent(variable);
  }
  function variableDefinition(variableName) {
    return {
      name: variableName,
      description: "설명이 정의되지 않았습니다.",
      ...(VARIABLES[variableName] || {}),
    };
  }
  function inputOrigins(variableName) {
    const variable = variableDefinition(variableName);
    const definition = variable.parent
      ? variableDefinition(variable.parent)
      : variable;
    const origins = definition.inputOrigins?.[name] || definition.origins || [];
    return origins
      .filter((origin) => {
        const producer = STEP_REFERENCE.find(
          (step) => step.name === origin.step,
        );
        return (
          VARIABLES[origin.variable] &&
          producer?.outputs.rows.some((row) => row.variable === origin.variable)
        );
      })
      .map((origin) => [origin.step, origin.variable]);
  }

  function block(title, content, headers, direction) {
    const section = element("section");
    section.append(element("h3", title));
    if (!content.rows.length) {
      section.append(element("p", content.text || "해당 항목이 없습니다."));
      return section;
    }
    const table = element("table");
    const head = element("thead");
    const headRow = element("tr");
    for (const label of headers) {
      const cell = element("th", label);
      cell.setAttribute("scope", "col");
      headRow.append(cell);
    }
    head.append(headRow);
    table.append(head);
    const body = element("tbody");
    for (const reference of content.rows) {
      const variable = variableDefinition(reference.variable);
      const row = [variable.name, variable.description];
      const tr = element("tr");
      if (direction === "output") tr.id = outputId(row[0]);
      row.forEach((value, index) => {
        const cell = element(index === 0 ? "th" : "td");
        if (index === 0) cell.setAttribute("scope", "row");
        if (index === 0) {
          const origins =
            direction === "input" ? inputOrigins(reference.variable) : [];
          if (!origins.length) cell.append(element("code", value));
          else
            origins.forEach(([producer, variable], sourceIndex) => {
              if (sourceIndex) cell.append(element("span", " / "));
              const link = element("a");
              link.setAttribute(
                "href",
                producer + ".html#" + encodeURIComponent(outputId(variable)),
              );
              link.setAttribute("title", producer + "의 Output: " + variable);
              link.append(element("code", sourceIndex ? producer : value));
              cell.append(link);
            });
        } else cell.textContent = value;
        tr.append(cell);
      });
      body.append(tr);
    }
    table.append(body);
    const wrapper = element("div", undefined, "table-scroll");
    wrapper.append(table);
    section.append(wrapper);
    return section;
  }

  const main = document.querySelector("main");
  if (!main) return;
  const name = main.dataset.step;
  if (!name) {
    const list = element("ul", undefined, "step-list");
    for (const step of STEP_REFERENCE) {
      const item = element("li");
      const link = element("a", step.name);
      link.setAttribute("href", step.name + ".html");
      item.append(
        link,
        element("span", step.group, "badge"),
        element("p", step.description),
      );
      list.append(item);
    }
    main.append(list);
    return;
  }
  const step = STEP_REFERENCE.find((entry) => entry.name === name);
  if (!step) {
    main.append(element("p", "해당 Step 문서를 찾을 수 없습니다."));
    return;
  }
  const nav = element("nav");
  nav.setAttribute("aria-label", "문서 탐색");
  const link = element("a", "← Step 목록", "back-link");
  link.setAttribute("href", "index.html");
  nav.append(link);
  const parameters = main.querySelector(".parameters");
  const article = element("article", undefined, "step");
  article.setAttribute("aria-labelledby", step.name);
  const heading = element("h2", step.name);
  heading.id = step.name;
  article.append(
    element("span", step.group, "badge"),
    heading,
    element("p", step.description),
    parameters,
    block("요구하는 Input 변수", step.inputs, ["변수", "설명"], "input"),
    block("제공하는 Output 변수", step.outputs, ["변수", "설명"], "output"),
  );
  main.append(nav, article);
  function scrollToOutput() {
    if (!window.location.hash) return;
    const target = document.getElementById(
      decodeURIComponent(window.location.hash.slice(1)),
    );
    if (target) target.scrollIntoView({ block: "center" });
  }
  window.addEventListener("hashchange", scrollToOutput);
  scrollToOutput();
})();
