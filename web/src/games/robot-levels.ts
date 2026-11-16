import type { Level } from './robot-maze'
// 每张岔路地图都包含已验收的积木程序。
export const extraMazeLevels: Level[] = [
  {
    "name": "森林岔路 1",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#.#...#",
      "#.#.#.#",
      "#.#.#.#",
      "#.#.#.#",
      "#...#.#",
      "#######"
    ],
    "start": {
      "x": 5,
      "y": 5,
      "direction": 2
    },
    "goal": {
      "x": 1,
      "y": 1
    },
    "gears": [
      {
        "x": 1,
        "y": 5
      },
      {
        "x": 1,
        "y": 4
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 5,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "森林岔路 2",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#.#...#",
      "#.###.#",
      "#.....#",
      "#####.#",
      "#.....#",
      "#######"
    ],
    "start": {
      "x": 3,
      "y": 1,
      "direction": 3
    },
    "goal": {
      "x": 1,
      "y": 1
    },
    "gears": [
      {
        "x": 5,
        "y": 5
      },
      {
        "x": 1,
        "y": 5
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 9,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "森林岔路 3",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#.....#",
      "#####.#",
      "#...#.#",
      "#.#.#.#",
      "#.#...#",
      "#######"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 2
    },
    "goal": {
      "x": 1,
      "y": 5
    },
    "gears": [
      {
        "x": 5,
        "y": 3
      },
      {
        "x": 3,
        "y": 5
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 6,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "森林岔路 4",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#...#.#",
      "###.#.#",
      "#.#...#",
      "#.###.#",
      "#.....#",
      "#######"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 3
    },
    "goal": {
      "x": 1,
      "y": 3
    },
    "gears": [
      {
        "x": 5,
        "y": 1
      },
      {
        "x": 2,
        "y": 5
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 7,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "森林岔路 5",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#.#...#",
      "#.###.#",
      "#.#...#",
      "#.#.#.#",
      "#...#.#",
      "#######"
    ],
    "start": {
      "x": 3,
      "y": 1,
      "direction": 3
    },
    "goal": {
      "x": 5,
      "y": 5
    },
    "gears": [
      {
        "x": 1,
        "y": 1
      },
      {
        "x": 1,
        "y": 2
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 10,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "森林岔路 6",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#.#...#",
      "#.###.#",
      "#...#.#",
      "###.#.#",
      "#.....#",
      "#######"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 1
    },
    "goal": {
      "x": 3,
      "y": 1
    },
    "gears": [
      {
        "x": 1,
        "y": 5
      },
      {
        "x": 4,
        "y": 1
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 8,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "森林岔路 7",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#.....#",
      "#####.#",
      "#.#...#",
      "#.#.###",
      "#.....#",
      "#######"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 3
    },
    "goal": {
      "x": 5,
      "y": 5
    },
    "gears": [
      {
        "x": 1,
        "y": 4
      },
      {
        "x": 5,
        "y": 1
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 9,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "forward"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "right",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "森林岔路 8",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#.....#",
      "#####.#",
      "#.....#",
      "#.#####",
      "#.....#",
      "#######"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 3
    },
    "goal": {
      "x": 5,
      "y": 5
    },
    "gears": [
      {
        "x": 3,
        "y": 3
      },
      {
        "x": 4,
        "y": 5
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 5,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "森林岔路 9",
    "chapter": 3,
    "concept": "分支与顺序",
    "description": "先收齐 2 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#######",
      "#.#...#",
      "#.#.#.#",
      "#...#.#",
      "#####.#",
      "#.....#",
      "#######"
    ],
    "start": {
      "x": 1,
      "y": 5,
      "direction": 1
    },
    "goal": {
      "x": 1,
      "y": 1
    },
    "gears": [
      {
        "x": 5,
        "y": 4
      },
      {
        "x": 2,
        "y": 3
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 5,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 1",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#...#.#",
      "#.#.#.#.#",
      "#.#.#...#",
      "#.#.#####",
      "#.#.....#",
      "#.#####.#",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 1
    },
    "goal": {
      "x": 7,
      "y": 1
    },
    "gears": [
      {
        "x": 2,
        "y": 7
      },
      {
        "x": 3,
        "y": 3
      },
      {
        "x": 7,
        "y": 2
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 9,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 2",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.....#.#",
      "#####.#.#",
      "#.....#.#",
      "#.#####.#",
      "#...#...#",
      "###.###.#",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 5,
      "y": 5,
      "direction": 1
    },
    "goal": {
      "x": 1,
      "y": 1
    },
    "gears": [
      {
        "x": 5,
        "y": 2
      },
      {
        "x": 1,
        "y": 7
      },
      {
        "x": 1,
        "y": 3
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 7,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 3",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.....#.#",
      "#####.#.#",
      "#.....#.#",
      "#.#####.#",
      "#.#.....#",
      "#.###.#.#",
      "#.....#.#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 0
    },
    "goal": {
      "x": 7,
      "y": 1
    },
    "gears": [
      {
        "x": 1,
        "y": 6
      },
      {
        "x": 3,
        "y": 5
      },
      {
        "x": 5,
        "y": 2
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 6,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward",
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 4",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.###.#.#",
      "#...#.#.#",
      "###.#.###",
      "#.#.#...#",
      "#.#.###.#",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 3,
      "y": 1,
      "direction": 3
    },
    "goal": {
      "x": 1,
      "y": 1
    },
    "gears": [
      {
        "x": 5,
        "y": 1
      },
      {
        "x": 7,
        "y": 5
      },
      {
        "x": 1,
        "y": 3
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 13,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 5",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#...#...#",
      "###.#.#.#",
      "#.#.#.#.#",
      "#.#.#.###",
      "#...#...#",
      "#.#####.#",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 3,
      "direction": 0
    },
    "goal": {
      "x": 1,
      "y": 1
    },
    "gears": [
      {
        "x": 3,
        "y": 1
      },
      {
        "x": 5,
        "y": 4
      },
      {
        "x": 5,
        "y": 7
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 12,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "forward"
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "right",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 6",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#...#...#",
      "###.#.###",
      "#...#...#",
      "#.#####.#",
      "#.#.....#",
      "#.#.###.#",
      "#...#...#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 3
    },
    "goal": {
      "x": 5,
      "y": 7
    },
    "gears": [
      {
        "x": 3,
        "y": 7
      },
      {
        "x": 4,
        "y": 5
      },
      {
        "x": 6,
        "y": 3
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 14,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "left",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "forward"
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 7",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.###.#.#",
      "#...#.#.#",
      "###.#.#.#",
      "#.#.#.#.#",
      "#.#.###.#",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 1
    },
    "goal": {
      "x": 3,
      "y": 1
    },
    "gears": [
      {
        "x": 4,
        "y": 7
      },
      {
        "x": 1,
        "y": 7
      },
      {
        "x": 3,
        "y": 7
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 10,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 8",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.#.#####",
      "#.#.....#",
      "#.#####.#",
      "#...#...#",
      "###.#.#.#",
      "#.....#.#",
      "#########"
    ],
    "start": {
      "x": 7,
      "y": 7,
      "direction": 0
    },
    "goal": {
      "x": 1,
      "y": 7
    },
    "gears": [
      {
        "x": 1,
        "y": 3
      },
      {
        "x": 4,
        "y": 3
      },
      {
        "x": 5,
        "y": 1
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 14,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right",
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "巡回收集 9",
    "chapter": 4,
    "concept": "循环与收集",
    "description": "先收齐 3 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#...#...#",
      "###.###.#",
      "#...#...#",
      "#.###.#.#",
      "#...#.#.#",
      "###.#.#.#",
      "#.....#.#",
      "#########"
    ],
    "start": {
      "x": 7,
      "y": 7,
      "direction": 3
    },
    "goal": {
      "x": 1,
      "y": 7
    },
    "gears": [
      {
        "x": 7,
        "y": 1
      },
      {
        "x": 7,
        "y": 5
      },
      {
        "x": 5,
        "y": 6
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 10,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 1",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.###.#.#",
      "#.#...#.#",
      "#.#.###.#",
      "#...#...#",
      "#####.###",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 7,
      "direction": 1
    },
    "goal": {
      "x": 3,
      "y": 1
    },
    "gears": [
      {
        "x": 2,
        "y": 7
      },
      {
        "x": 6,
        "y": 1
      },
      {
        "x": 7,
        "y": 3
      },
      {
        "x": 4,
        "y": 3
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 12,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "forward"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "forward"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 2",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#...#...#",
      "###.###.#",
      "#.#.#...#",
      "#.#.#.###",
      "#...#...#",
      "#.#####.#",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 3,
      "direction": 0
    },
    "goal": {
      "x": 5,
      "y": 1
    },
    "gears": [
      {
        "x": 4,
        "y": 7
      },
      {
        "x": 1,
        "y": 5
      },
      {
        "x": 3,
        "y": 2
      },
      {
        "x": 6,
        "y": 7
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 11,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "forward"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 3",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.#.###.#",
      "#.#.#.#.#",
      "#.#.#.#.#",
      "#.#.#.#.#",
      "#.#.#.#.#",
      "#...#...#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 2
    },
    "goal": {
      "x": 5,
      "y": 3
    },
    "gears": [
      {
        "x": 6,
        "y": 7
      },
      {
        "x": 3,
        "y": 3
      },
      {
        "x": 6,
        "y": 1
      },
      {
        "x": 1,
        "y": 7
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 6,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 4",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.....#.#",
      "#####.#.#",
      "#.....#.#",
      "#.#####.#",
      "#.#.....#",
      "#.#.###.#",
      "#...#...#",
      "#########"
    ],
    "start": {
      "x": 7,
      "y": 1,
      "direction": 0
    },
    "goal": {
      "x": 5,
      "y": 7
    },
    "gears": [
      {
        "x": 2,
        "y": 3
      },
      {
        "x": 7,
        "y": 4
      },
      {
        "x": 4,
        "y": 3
      },
      {
        "x": 5,
        "y": 1
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 18,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 5",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.#####.#",
      "#.....#.#",
      "#####.#.#",
      "#...#...#",
      "#.#####.#",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 2
    },
    "goal": {
      "x": 3,
      "y": 5
    },
    "gears": [
      {
        "x": 7,
        "y": 7
      },
      {
        "x": 3,
        "y": 1
      },
      {
        "x": 5,
        "y": 4
      },
      {
        "x": 5,
        "y": 7
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 13,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 6",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.#####.#",
      "#.......#",
      "#######.#",
      "#.#.....#",
      "#.#.#####",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 5,
      "direction": 2
    },
    "goal": {
      "x": 7,
      "y": 7
    },
    "gears": [
      {
        "x": 3,
        "y": 7
      },
      {
        "x": 5,
        "y": 3
      },
      {
        "x": 4,
        "y": 5
      },
      {
        "x": 7,
        "y": 3
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 10,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 7",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.#.###.#",
      "#.#.#...#",
      "#.#.#.#.#",
      "#.#.#.#.#",
      "#.###.#.#",
      "#.....#.#",
      "#########"
    ],
    "start": {
      "x": 7,
      "y": 7,
      "direction": 2
    },
    "goal": {
      "x": 3,
      "y": 5
    },
    "gears": [
      {
        "x": 3,
        "y": 4
      },
      {
        "x": 1,
        "y": 3
      },
      {
        "x": 1,
        "y": 7
      },
      {
        "x": 7,
        "y": 6
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 12,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "forward",
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "left",
          "forward",
          "forward",
          "forward",
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left",
          "forward",
          "forward",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 8",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#...#...#",
      "###.#.###",
      "#.#.#...#",
      "#.#.###.#",
      "#.#.....#",
      "#.#####.#",
      "#.......#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 1,
      "direction": 2
    },
    "goal": {
      "x": 7,
      "y": 1
    },
    "gears": [
      {
        "x": 3,
        "y": 1
      },
      {
        "x": 7,
        "y": 4
      },
      {
        "x": 3,
        "y": 4
      },
      {
        "x": 7,
        "y": 7
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 13,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      }
    ]
  },
  {
    "name": "长程调度 9",
    "chapter": 5,
    "concept": "多目标规划",
    "description": "先收齐 4 枚零件，再回到充电站。岔路里的零件也不能漏掉。",
    "rows": [
      "#########",
      "#.#.....#",
      "#.#.###.#",
      "#.#...#.#",
      "#.#####.#",
      "#...#...#",
      "###.#.#.#",
      "#.....#.#",
      "#########"
    ],
    "start": {
      "x": 1,
      "y": 7,
      "direction": 0
    },
    "goal": {
      "x": 1,
      "y": 1
    },
    "gears": [
      {
        "x": 3,
        "y": 5
      },
      {
        "x": 7,
        "y": 4
      },
      {
        "x": 4,
        "y": 3
      },
      {
        "x": 2,
        "y": 7
      }
    ],
    "commands": [
      "forward",
      "left",
      "right"
    ],
    "repeat": true,
    "budget": 19,
    "hint": "先在地图上找到所有零件。把相同的前进动作放入重复积木，经过岔路后再规划返回路线。",
    "reference": [
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "forward"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "left",
          "forward",
          "forward",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward",
          "left",
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "left"
        ]
      },
      {
        "type": "forward"
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 3,
        "body": [
          "forward",
          "forward",
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "right",
          "forward",
          "forward"
        ]
      },
      {
        "type": "left"
      },
      {
        "type": "repeat",
        "count": 2,
        "body": [
          "forward"
        ]
      },
      {
        "type": "right"
      },
      {
        "type": "repeat",
        "count": 4,
        "body": [
          "forward"
        ]
      }
    ]
  }
]
