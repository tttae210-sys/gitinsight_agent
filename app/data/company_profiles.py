"""
IT 기업별 인재상 및 면접 스타일 데이터베이스
"""

COMPANY_PROFILES = {
    "카카오": {
        "name": "카카오",
        "values": [
            "사용자 중심 사고", "빠른 실행력", "열린 소통", "지속적 학습", "창의적 문제 해결"
        ],
        "culture": "수평적 조직문화, 자율과 책임, 사용자 경험 우선",
        "interview_style": "실무 중심, 코드 리뷰 스타일, 사용자 관점 강조",
        "tech_focus": ["대용량 트래픽", "마이크로서비스", "클라우드", "데이터 파이프라인", "사용자 경험"],
        "recent_trends": ["AI/ML 서비스", "클라우드 네이티브", "개인화 추천", "실시간 처리"]
    },
    "네이버": {
        "name": "네이버",
        "values": [
            "기술로 연결되는 세상", "글로벌 경쟁력", "전문성 추구", "도전정신", "협업"
        ],
        "culture": "기술 중심 문화, 전문성 존중, 글로벌 마인드",
        "interview_style": "깊이 있는 기술 질문, CS 기초 중시, 확장성 고려",
        "tech_focus": ["검색 엔진", "AI", "클라우드", "글로벌 서비스", "플랫폼"],
        "recent_trends": ["HyperCLOVA X", "클라우드 플랫폼", "AI 검색", "웹툰/웹소설 기술"]
    },
    "쿠팡": {
        "name": "쿠팡",
        "values": [
            "고객 obsession", "소유의식", "빠른 실행", "혁신", "성장 마인드"
        ],
        "culture": "스타트업 문화, 빠른 의사결정, 결과 중심, 글로벌 기준",
        "interview_style": "시스템 설계 중시, 대규모 서비스 경험, 성능 최적화",
        "tech_focus": ["이커머스", "물류 시스템", "실시간 처리", "대규모 데이터", "글로벌 인프라"],
        "recent_trends": ["로켓배송 기술", "AI 추천", "클라우드 인프라", "마이크로서비스"]
    },
    "토스": {
        "name": "토스",
        "values": [
            "고객 중심", "단순함의 힘", "투명성", "성장", "협력"
        ],
        "culture": "고객 경험 최우선, 데이터 기반 의사결정, 빠른 실험",
        "interview_style": "사용자 경험 중시, 데이터 분석 능력, 보안 의식",
        "tech_focus": ["핀테크", "보안", "실시간 처리", "사용자 경험", "데이터 분석"],
        "recent_trends": ["오픈뱅킹", "마이데이터", "블록체인", "AI 기반 금융서비스"]
    },
    "업스테이지": {
        "name": "업스테이지",
        "values": [
            "AI 기술로 현실 문제 해결", "세계 무대 도전", "주도적 태도", "깊이 있는 기술적 전문성", "Upstage Way 부합"
        ],
        "culture": "주도적으로 문제를 정의하고 해결책을 설계하는 문화, 기술 전문성 존중, 세계 최고 AI 기술 추구",
        "interview_style": "기술적 깊이 검증, 문제 해결 주도성, AI 실무 구현 능력, Upstage Way 적합성 평가",
        "tech_focus": ["LLM", "AI/ML", "자연어처리", "컴퓨터 비전", "멀티모달 AI"],
        "recent_trends": ["Solar LLM", "Document AI", "Private LLM", "AI 에이전트", "RAG 시스템"]
    }
}
COMPANY_PROFILES.update({
    "라인": {
        "name": "라인",
        "values": [
            "사용자 우선", "글로벌 마인드", "창의적 도전", "열린 소통", "지속적 성장"
        ],
        "culture": "글로벌 문화, 다양성 존중, 사용자 경험 중시",
        "interview_style": "글로벌 서비스 경험, 다국어 지원, 확장성",
        "tech_focus": ["메신저", "AI", "블록체인", "게임", "광고 플랫폼"],
        "recent_trends": ["LINE AI", "NFT/블록체인", "메타버스", "클라우드 서비스"]
    },
    "배달의민족": {
        "name": "배달의민족",
        "values": [
            "좋은 음식을 먹고 싶은 곳에서", "성장", "도전", "소통", "즐거움"
        ],
        "culture": "창의적이고 자유로운 문화, 사용자 경험 중시",
        "interview_style": "창의적 문제 해결, 사용자 관점, 빠른 개발",
        "tech_focus": ["O2O", "실시간 매칭", "지도 서비스", "결제", "물류"],
        "recent_trends": ["배달 로봇", "AI 추천", "실시간 배송 최적화", "키오스크"]
    },
    "당근마켓": {
        "name": "당근마켓",
        "values": [
            "지역 사회 연결", "신뢰", "따뜻한 기술", "성장", "투명성"
        ],
        "culture": "지역 중심, 사회적 가치, 사용자 신뢰",
        "interview_style": "사회적 가치 이해, 지역 서비스 경험, 신뢰 구축",
        "tech_focus": ["로컬 서비스", "신뢰도 시스템", "추천 알고리즘", "커뮤니티"],
        "recent_trends": ["동네생활", "AI 가격 추천", "지역 광고", "안전 거래"]
    },
    "우아한형제들": {
        "name": "우아한형제들",
        "values": [
            "배달이 일상을 더 풍요롭게", "고객 만족", "기술 혁신", "협업", "성장"
        ],
        "culture": "기술로 사회 문제 해결, 혁신적 사고",
        "interview_style": "기술적 도전 의식, 확장성 고려, 최적화 경험",
        "tech_focus": ["배달 플랫폼", "실시간 최적화", "물류", "결제", "광고"],
        "recent_trends": ["배달 로봇", "드론 배달", "AI 배송 최적화", "클라우드 키친"]
    }
})

FIELD_TRENDS = {
    "백엔드 개발": {
        "trends": [
            "마이크로서비스 아키텍처", "서버리스 컴퓨팅", "컨테이너 오케스트레이션", 
            "이벤트 드리븐 아키텍처", "GraphQL", "gRPC", "클라우드 네이티브",
            "옵저버빌리티", "DevSecOps", "멀티 클라우드"
        ],
        "skills": [
            "Kubernetes", "Docker", "AWS/GCP/Azure", "Redis", "Kafka",
            "Elasticsearch", "Prometheus", "Grafana", "Terraform"
        ]
    },
    "프론트엔드 개발": {
        "trends": [
            "React 18", "Next.js 14", "Vue 3 Composition API", "Web Components",
            "Micro Frontends", "Server Components", "웹 어셈블리", "PWA",
            "웹 접근성", "Core Web Vitals", "헤드리스 CMS"
        ],
        "skills": [
            "TypeScript", "Webpack/Vite", "Tailwind CSS", "Storybook",
            "Cypress", "Jest", "React Query", "Zustand"
        ]
    },
    "풀스택 개발": {
        "trends": [
            "JAMstack", "Edge Computing", "실시간 협업 도구", "Low Code/No Code",
            "API-First 개발", "모노레포", "풀스택 프레임워크", "웹3 통합"
        ],
        "skills": [
            "Next.js", "Nuxt.js", "SvelteKit", "Remix", "tRPC", "Prisma"
        ]
    },
    "DevOps/인프라": {
        "trends": [
            "GitOps", "플랫폼 엔지니어링", "FinOps", "멀티 클라우드", "에지 컴퓨팅",
            "서비스 메시", "옵저버빌리티", "카오스 엔지니어링", "보안 자동화"
        ],
        "skills": [
            "Kubernetes", "Terraform", "Ansible", "Jenkins", "ArgoCD",
            "Istio", "Prometheus", "ELK Stack", "Docker"
        ]
    }
}
FIELD_TRENDS.update({
    "데이터 엔지니어": {
        "trends": [
            "실시간 데이터 파이프라인", "데이터 메시", "레이크하우스", "스트리밍 분석",
            "데이터 품질 관리", "MLOps", "연합 학습", "데이터 거버넌스"
        ],
        "skills": [
            "Apache Spark", "Kafka", "Airflow", "dbt", "Snowflake",
            "Databricks", "Kubernetes", "Python/Scala"
        ]
    },
    "ML/AI 엔지니어": {
        "trends": [
            "LLM/GPT 활용", "멀티모달 AI", "엣지 AI", "MLOps", "AutoML",
            "연합 학습", "설명 가능한 AI", "AI 윤리", "벡터 데이터베이스"
        ],
        "skills": [
            "PyTorch/TensorFlow", "Hugging Face", "MLflow", "Kubeflow",
            "Ray", "ONNX", "TensorRT", "Vector DB"
        ]
    },
    "모바일 앱 개발": {
        "trends": [
            "크로스 플랫폼", "앱 클립/인스턴트 앱", "AR/VR 통합", "5G 활용",
            "앱 보안", "오프라인 우선", "마이크로 인터랙션", "다크 모드"
        ],
        "skills": [
            "React Native", "Flutter", "SwiftUI", "Kotlin Compose",
            "WebRTC", "Core ML", "ARKit/ARCore"
        ]
    },
    "게임 개발": {
        "trends": [
            "메타버스", "클라우드 게이밍", "크로스 플랫폼", "블록체인 게임",
            "AI NPC", "실시간 멀티플레이", "게임 스트리밍", "웹 게임"
        ],
        "skills": [
            "Unity", "Unreal Engine", "WebGL", "WebAssembly",
            "Photon", "Mirror", "Socket.IO"
        ]
    }
})